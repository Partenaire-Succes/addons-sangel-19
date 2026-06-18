from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re
import logging

_logger = logging.getLogger(__name__)


class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'
    _rec_name = 'customer_id'

    customer_id = fields.Char(
        string="ID client",
        copy=False,
        tracking=True,
        index=True
    )
    customer_account = fields.Char(
        string="Compte personnel",
        help="Compte des personnel SANgel (ex: 42110001 pour le personnel de SANGEL).",
    )

    type_location = fields.Selection([
        ('abj', 'Abidjan'),
        ('int', 'Interieur'),
    ], string='Localite', default='abj',)

    discount_eligible = fields.Boolean(
        string="Éligible à la remise",
        default=False,
        help="Cochez si ce client peut bénéficier d'une remise.",
        tracking = True
    )

    discount_percentage = fields.Float(
        string="Pourcentage de remise",
        default=0.0,
        help="Entrez le pourcentage de remise que ce client bénéficiera.",
        tracking=True
    )

    is_airsi_eligible = fields.Boolean(
        string="Éligible à l'AIRSI",
        default=False,
        help="Cochez si ce client est assujetti à l'AIRSI.",
        tracking = True
    )

    code_family = fields.Char(
        string="Code famille",
        tracking = True
    )

    secondary_responsible_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsable secondaire",
        tracking = True
    )

    primary_responsible_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsable principal",
        tracking = True
    )

    create_date_sage = fields.Datetime(string="Date création SAGE")

    update_date_sage = fields.Datetime(string="Date MAJ SAGE")

    discount_start_date = fields.Date(
        string="Date de début remise",
        help="La remise est applicable uniquement à partir de cette date.",
        tracking = True
    )

    discount_end_date = fields.Date(
        string="Date de fin remise",
        help="La remise cesse d’être applicable après cette date.",
        tracking = True
    )

    _sql_constraints = [
        ('customer_id_unique', 'unique(customer_id)', 'Le ID client doit être unique !')
    ]

    loyalty_card_ids = fields.One2many(
        comodel_name="loyalty.card",
        inverse_name="partner_id",
        string="Cartes de fidélité"
    )

    no_loyalty_points = fields.Boolean(
        string='Exclure des points de fidélité',
        default=False,
        tracking=True,
        help="Si coché, ce client ne cumule aucun point de fidélité (ni en caisse ni sur commande).",
    )

    no_promotion = fields.Boolean(
        string='Exclure des promotions',
        default=False,
        tracking=True,
        help="Si coché, aucune remise promotionnelle ne sera appliquée à ce client en caisse.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        """Expose no_loyalty_points et no_promotion au POS pour fonctionnement hors-ligne."""
        result = super()._load_pos_data_fields(config)
        result.append('no_loyalty_points')
        result.append('no_promotion')
        return result

    # @api.depends('name', 'customer_id')
    # def _compute_display_name(self):
    #     for partner in self:
    #         if partner.customer_id:
    #             partner.display_name = f"{partner.customer_id}"
    #         else:
    #             partner.display_name = partner.name

    def _propagate_barcode_to_all_companies(self, barcode_value):
        """Écrit barcode sur toutes les sociétés actives (champ company_dependent)."""
        if not barcode_value:
            return
        companies = self.env['res.company'].sudo().search([])
        for partner in self:
            for company in companies:
                try:
                    with self.env.cr.savepoint():
                        partner.with_company(company).with_context(
                            no_recompute=True,
                            skip_barcode_propagation=True,
                        ).write({'barcode': barcode_value})
                except Exception as e:
                    _logger.warning(
                        "[BARCODE SYNC] Barcode '%s' → partenaire %s / société %s : %s",
                        barcode_value, partner.id, company.id, str(e)
                    )

    def _assign_barcode_from_customer_id(self, cid):
        """Assigne barcode = customer_id si commence par '10' ou '20' et barcode vide."""
        if not cid or not cid.startswith(('10', '20')):
            return
        for partner in self:
            if not partner.barcode:
                partner._propagate_barcode_to_all_companies(cid)

    @api.model_create_multi
    def create(self, vals_list):
        partners = super(ResPartnerInherit, self).create(vals_list)
        for partner in partners:
            cid = partner.customer_id or ''
            partner._assign_barcode_from_customer_id(cid)
        return partners

    def write(self, vals):
        if self.env.context.get('skip_barcode_propagation'):
            return super(ResPartnerInherit, self).write(vals)
        result = super(ResPartnerInherit, self).write(vals)
        if 'customer_id' in vals:
            cid = vals.get('customer_id') or ''
            self._assign_barcode_from_customer_id(cid)
        elif 'barcode' in vals and vals.get('barcode'):
            self._propagate_barcode_to_all_companies(vals['barcode'])
        return result

    def action_sync_barcode_from_customer_id(self):
        """Migration : assigne barcode = customer_id pour les partenaires existants
        dont customer_id commence par '10' ou '20' et dont le barcode est vide."""
        BATCH_SIZE = 500

        partner_ids = self.env['res.partner'].search([
            '|',
            ('customer_id', 'like', '10%'),
            ('customer_id', 'like', '20%'),
            ('barcode', '=', False),
        ]).ids

        total = len(partner_ids)
        updated = 0
        skipped = 0
        _logger.info("[BARCODE SYNC] Démarrage — %d partenaires à traiter.", total)

        for idx, pid in enumerate(partner_ids):
            partner = self.env['res.partner'].browse(pid)
            cid = partner.customer_id or ''
            if not cid.startswith(('10', '20')):
                continue
            try:
                partner._propagate_barcode_to_all_companies(cid)
                updated += 1
            except Exception as e:
                _logger.warning(
                    "[BARCODE SYNC] Échec partenaire %s (customer_id=%s) : %s",
                    pid, cid, str(e)
                )
                skipped += 1

            if (idx + 1) % BATCH_SIZE == 0:
                self.env.cr.commit()
                self.env.invalidate_all()
                _logger.info(
                    "[BARCODE SYNC] Commit %d/%d — %d ok, %d ignorés.",
                    idx + 1, total, updated, skipped
                )

        self.env.cr.commit()
        _logger.info("[BARCODE SYNC] Terminé — %d mis à jour, %d ignorés sur %d.", updated, skipped, total)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Synchronisation terminée'),
                'message': _(
                    '%(updated)d client(s) mis à jour. %(skipped)d ignoré(s) sur %(total)d.',
                    updated=updated, skipped=skipped, total=total
                ),
                'type': 'success',
                'sticky': True,
            },
        }

    def action_fill_missing_company_barcodes(self):
        """Propage le barcode (= customer_id) sur toutes les sociétés pour les partenaires
        dont customer_id commence par '10' ou '20', qu'ils aient déjà un barcode partiel ou non."""
        BATCH_SIZE = 500

        partners = self.env['res.partner'].search([
            '|',
            ('customer_id', 'like', '10%'),
            ('customer_id', 'like', '20%'),
        ])

        total = len(partners)
        updated = 0
        skipped = 0
        companies = self.env['res.company'].sudo().search([])
        _logger.info("[BARCODE FILL] Démarrage — %d partenaires / %d sociétés.", total, len(companies))

        for idx, partner in enumerate(partners):
            cid = partner.customer_id or ''
            if not cid.startswith(('10', '20')):
                continue

            # Détecte les sociétés où le barcode est absent ou différent du customer_id
            missing = []
            for company in companies:
                current = partner.with_company(company).barcode
                if current != cid:
                    missing.append(company)

            if not missing:
                continue

            for company in missing:
                try:
                    with self.env.cr.savepoint():
                        partner.with_company(company).with_context(
                            no_recompute=True,
                            skip_barcode_propagation=True,
                        ).write({'barcode': cid})
                except Exception as e:
                    _logger.warning(
                        "[BARCODE FILL] Barcode '%s' → partenaire %s / société %s : %s",
                        cid, partner.id, company.id, str(e)
                    )
                    skipped += 1
                    continue
            updated += 1

            if (idx + 1) % BATCH_SIZE == 0:
                self.env.cr.commit()
                self.env.invalidate_all()
                _logger.info(
                    "[BARCODE FILL] Commit %d/%d — %d ok, %d ignorés.",
                    idx + 1, total, updated, skipped
                )

        self.env.cr.commit()
        _logger.info("[BARCODE FILL] Terminé — %d mis à jour, %d ignorés sur %d.", updated, skipped, total)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Synchronisation terminée'),
                'message': _(
                    '%(updated)d client(s) complétés. %(skipped)d ignoré(s) sur %(total)d.',
                    updated=updated, skipped=skipped, total=total
                ),
                'type': 'success',
                'sticky': True,
            },
        }

    @api.onchange('discount_eligible')
    def onchange_discount_start_date(self):
        for rec in self:
            if rec.discount_eligible:
                rec.discount_start_date = fields.Date.today()
            else:
                rec.discount_start_date = False


    def remove_duplicate_partners(self):
        partners = self.env['res.partner'].search([
            ('customer_id', '!=', False)
        ], order='customer_id, id')

        seen = {}
        duplicates = self.env['res.partner']

        for partner in partners:
            key = partner.customer_id.strip()

            if key in seen:
                duplicates |= partner
            else:
                seen[key] = partner

        # ⚠️ suppression
        duplicates.unlink()

        return True