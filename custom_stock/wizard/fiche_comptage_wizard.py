# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FicheComptageWizard(models.TransientModel):
    _name = 'fiche.comptage.wizard'
    _description = 'Wizard Fiche de Comptage'

    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
    )
    inventory_mode = fields.Selection([
        ('normal', 'Inventaire (par code)'),
        ('libre',  'Inventaire Libre'),
    ], string='Mode', required=True, default='normal')

    # ── Filtres mode normal ────────────────────────────────────────
    code_inventory_ids = fields.Many2many(
        'code.inventory',
        string='Codes Inventaire',
        help="Laisser vide pour tous les codes",
    )
    code_category_ids = fields.Many2many(
        'code.category.inventory',
        string='Catégories Code Inventaire',
        help="Laisser vide pour toutes les catégories",
    )

    # ── Sélection mode libre ───────────────────────────────────────
    product_ids = fields.Many2many(
        'product.product',
        string='Produits',
        domain=[('type', '=', 'consu'), ('active', '=', True)],
    )

    article_count = fields.Integer(
        string="Nombre d'articles",
        compute='_compute_article_count',
    )

    @api.depends('inventory_mode', 'company_id', 'code_inventory_ids', 'code_category_ids', 'product_ids')
    def _compute_article_count(self):
        for rec in self:
            if rec.inventory_mode == 'normal':
                rec.article_count = len(rec._get_quants())
            else:
                rec.article_count = len(rec.product_ids)

    def _get_quants(self):
        """Retourne les quants filtrés (mode normal)."""
        company = self.company_id
        domain = [
            ('location_id.usage', '=', 'internal'),
            ('company_id', '=', company.id),
            ('product_id.active', '=', True),
            ('product_id.type', '=', 'consu'),
        ]
        if self.code_inventory_ids:
            domain.append(('code_inventory_id', 'in', self.code_inventory_ids.ids))
        if self.code_category_ids:
            domain.append(('code_inventory_id.code_category_id', 'in', self.code_category_ids.ids))

        # Filtre statut 'C' pour la société sélectionnée (en SQL via les IDs valides)
        valid_tmpl_ids = self.env['product.company.status'].search([
            ('company_id', '=', company.id),
            ('status_id.code', '=', 'C'),
        ]).mapped('product_id').ids
        domain.append(('product_tmpl_id', 'in', valid_tmpl_ids))

        # Filtre allowed_company_ids si le champ existe
        if self.env['product.template']._fields.get('allowed_company_ids'):
            domain += [
                '|',
                ('product_tmpl_id.allowed_company_ids', '=', False),
                ('product_tmpl_id.allowed_company_ids', 'in', [company.id]),
            ]

        return self.env['stock.quant'].search(domain, order='code_inventory_id, product_id')

    def _get_libre_products(self):
        """Retourne les produits sélectionnés (mode libre)."""
        return self.product_ids.sorted(key=lambda p: (p.categ_id.name or '', p.default_code or ''))

    def action_print_fiche_comptage(self):
        self.ensure_one()
        if self.inventory_mode == 'normal':
            if not self._get_quants():
                raise UserError(_("Aucun produit trouvé pour les critères sélectionnés."))
        else:
            if not self.product_ids:
                raise UserError(_("Veuillez sélectionner au moins un produit."))
        return self.env.ref('custom_stock.action_report_fiche_comptage').report_action(self)
