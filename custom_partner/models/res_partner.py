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

    @api.model
    def _load_pos_data_fields(self, config):
        """Expose no_loyalty_points au POS pour fonctionnement hors-ligne."""
        result = super()._load_pos_data_fields(config)
        result.append('no_loyalty_points')
        return result

    # @api.depends('name', 'customer_id')
    # def _compute_display_name(self):
    #     for partner in self:
    #         if partner.customer_id:
    #             partner.display_name = f"{partner.customer_id}"
    #         else:
    #             partner.display_name = partner.name

    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        # Recherche par customer_id si l’utilisateur tape un ID
        partners = self.search([('customer_id', operator, name)] + args, limit=limit)
        if not partners:
            # Sinon recherche standard (par nom, email, etc.)
            partners = super().name_search(name, args=args, operator=operator, limit=limit)
        return partners.name_get()

    def _assign_barcode_from_customer_id(self, cid):
        """Assigne barcode = customer_id si commence par '20' et barcode vide.
        Utilise un savepoint pour éviter de corrompre la transaction principale
        en cas d'erreur JSONB sur le champ barcode."""
        if not cid or not cid.startswith('20'):
            return
        for partner in self:
            if not partner.barcode:
                try:
                    with self.env.cr.savepoint():
                        partner.with_context(no_recompute=True).write({'barcode': cid})
                except Exception as e:
                    _logger.warning(
                        "[BARCODE SYNC] Impossible d'assigner le barcode '%s' au partenaire %s : %s",
                        cid, partner.id, str(e)
                    )

    @api.model_create_multi
    def create(self, vals_list):
        partners = super(ResPartnerInherit, self).create(vals_list)
        for partner in partners:
            cid = partner.customer_id or ''
            partner._assign_barcode_from_customer_id(cid)
        return partners

    def write(self, vals):
        result = super(ResPartnerInherit, self).write(vals)
        if 'customer_id' in vals:
            cid = vals.get('customer_id') or ''
            self._assign_barcode_from_customer_id(cid)
        return result

    def action_sync_barcode_from_customer_id(self):
        """Migration : assigne barcode = customer_id pour les partenaires existants
        dont customer_id commence par '20' et dont le barcode est vide.
        Commit tous les 500 enregistrements pour éviter les transactions trop longues."""
        BATCH_SIZE = 500

        partner_ids = self.env['res.partner'].search([
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
            if not cid.startswith('20'):
                continue
            try:
                with self.env.cr.savepoint():
                    partner.with_context(no_recompute=True).write({'barcode': cid})
                    updated += 1
            except Exception as e:
                _logger.warning(
                    "[BARCODE SYNC] Échec partenaire %s (customer_id=%s) : %s",
                    pid, cid, str(e)
                )
                skipped += 1

            # Commit intermédiaire + libération mémoire tous les BATCH_SIZE
            if (idx + 1) % BATCH_SIZE == 0:
                self.env.cr.commit()
                self.env.invalidate_all()
                _logger.info(
                    "[BARCODE SYNC] Commit %d/%d — %d ok, %d ignorés.",
                    idx + 1, total, updated, skipped
                )

        # Commit final
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