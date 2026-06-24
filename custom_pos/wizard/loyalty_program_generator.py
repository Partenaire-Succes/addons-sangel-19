# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class LoyaltyProgramGenerator(models.TransientModel):
    _name = 'loyalty.program.generator'
    _description = 'Générateur de remises multi-sociétés'

    product_ids = fields.Many2many(
        'product.product',
        string='Produits',
        required=True,
        domain=[('sale_ok', '=', True)],
    )
    minimum_qty = fields.Integer(
        string='Quantité minimum (acheter)',
        default=2,
        required=True,
    )
    reward_qty = fields.Integer(
        string='Quantité offerte',
        default=1,
        required=True,
    )
    company_ids = fields.Many2many(
        'res.company',
        string='Sociétés',
        required=True,
    )
    date_from = fields.Date(string='Date début')
    date_to = fields.Date(string='Date fin')
    pos_ok = fields.Boolean(string='Disponible en POS', default=True)
    skip_existing = fields.Boolean(
        string='Ignorer si programme existe déjà',
        default=True,
    )

    @api.constrains('minimum_qty', 'reward_qty')
    def _check_quantities(self):
        for rec in self:
            if rec.minimum_qty < 1:
                raise UserError(_("La quantité minimum doit être au moins 1."))
            if rec.reward_qty < 1:
                raise UserError(_("La quantité offerte doit être au moins 1."))

    def _find_existing_program(self, product, company):
        return self.env['loyalty.program'].search([
            ('company_id', '=', company.id),
            ('active', '=', True),
            ('rule_ids.product_ids', 'in', [product.id]),
            ('reward_ids.reward_type', '=', 'product'),
        ], limit=1)

    def _build_program_name(self, product, company):
        code = product.default_code or str(product.id)
        return 'MECANISME %s ACHETES %s OFFERT - %s %s' % (
            self.minimum_qty, self.reward_qty, code, company.name,
        )

    def _create_program(self, product, company):
        """Crée un programme en 2 étapes pour éviter l'écrasement par le compute."""
        pts = float(self.minimum_qty)

        # Étape 1 — le compute _compute_from_program_type crée les defaults
        program = self.env['loyalty.program'].with_company(company).create({
            'name': self._build_program_name(product, company),
            'program_type': 'promotion',
            'company_id': company.id,
            'currency_id': company.currency_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'pos_ok': self.pos_ok,
        })

        # Étape 2 — on écrase les defaults avec nos valeurs
        if program.rule_ids:
            program.rule_ids[0].write({
                'reward_point_mode': 'order',
                'reward_point_amount': pts,
                'minimum_qty': self.minimum_qty,
                'minimum_amount': 0,
                'minimum_amount_tax_mode': 'incl',
                'product_ids': [(6, 0, [product.id])],
            })

        if program.reward_ids:
            program.reward_ids[0].write({
                'reward_type': 'product',
                'reward_product_id': product.id,
                'reward_product_qty': self.reward_qty,
                'required_points': pts,
            })

        return program

    def action_generate(self):
        self.ensure_one()
        created = self.env['loyalty.program']
        skipped = []

        for product in self.product_ids:
            for company in self.company_ids:
                if self.skip_existing:
                    existing = self._find_existing_program(product, company)
                    if existing:
                        skipped.append('%s — %s' % (
                            product.display_name, company.name,
                        ))
                        continue

                program = self._create_program(product, company)
                created |= program

        if not created and skipped:
            raise UserError(_(
                "Aucun programme créé.\n"
                "Tous les programmes existent déjà :\n%s"
            ) % '\n'.join('  • %s' % s for s in skipped))

        if not created and not skipped:
            raise UserError(_("Aucun produit ou société sélectionné."))

        msg = _("%s programme(s) créé(s).") % len(created)
        if skipped:
            msg += _("\n%s ignoré(s) (déjà existants).") % len(skipped)

        action = self.env['ir.actions.act_window']._for_xml_id(
            'custom_pos.action_loyalty_program_promo'
        )
        action['name'] = msg
        action['domain'] = [('id', 'in', created.ids)]
        return action
