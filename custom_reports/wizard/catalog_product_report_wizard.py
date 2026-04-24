# -*- coding: utf-8 -*-
from odoo import models, fields
import datetime
from collections import defaultdict
from odoo.exceptions import ValidationError
import logging
import base64

_logger = logging.getLogger(__name__)

class ProductReportWizard(models.TransientModel):
    _name = 'product.report.wizard'
    _description = 'Wizard Catalogue Articles'

    categ_ids = fields.Many2many(
        'product.category',
        string='Familles',
        help='Laisser vide pour toutes les catégories'
    )
    active_products_only = fields.Boolean(
        string='Produits actifs uniquement',
        default=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company,
        readonly=True
    )

    def action_print_report(self):
        self.ensure_one()
        domain = []
        # domain = [('current_company_status_id.code', '=', 'C')]

        if self.active_products_only:
            domain.append(('active', '=', True))
        if self.company_id:
            domain.append(('allowed_company_ids', 'in', [self.company_id.id]))
        if self.categ_ids:
            domain.append(('categ_id', 'child_of', self.categ_ids.ids))

        products = self.env['product.template'].search(domain)
        products = products.filtered(
            lambda p: p.current_company_status_id and p.current_company_status_id.code == 'C'
        )
        _logger.info("PRODUCTS FOUND: %s", len(products))

        if not products:
            raise ValidationError('Aucun article trouvé avec ces critères.')

        return self.env.ref(
            'custom_reports.action_report_product_template'
        ).report_action(products)

    
    def action_print_excel(self):
        """Exporte le catalogue en fichier Excel (.xlsx)."""
        self.ensure_one()
 
        # ── Même domaine que action_print_report ──────────────────────────────
        domain = []
        if self.active_products_only:
            domain.append(('active', '=', True))
        if self.company_id:
            domain.append(('allowed_company_ids', 'in', [self.company_id.id]))
        if self.categ_ids:
            domain.append(('categ_id', 'child_of', self.categ_ids.ids))
 
        products = self.env['product.template'].search(domain)
        products = products.filtered(
            lambda p: p.current_company_status_id
                      and p.current_company_status_id.code == 'C'
        )
 
        if not products:
            raise ValidationError('Aucun article trouvé avec ces critères.')
 
        # ── Génération du fichier ─────────────────────────────────────────────
        report = self.env['report.custom_reports.catalogue_xlsx']
        xlsx_bytes = report.generate(products, self.company_id)
 
        # ── Stockage en pièce jointe temporaire ───────────────────────────────
        today  = fields.Date.today().strftime('%Y%m%d')
        fname  = f"Catalogue_Articles_{today}.xlsx"
        attach = self.env['ir.attachment'].create({
            'name':       fname,
            'type':       'binary',
            'datas':      base64.b64encode(xlsx_bytes),
            'res_model':  self._name,
            'res_id':     self.id,
            'mimetype':   'application/vnd.openxmlformats-officedocument'
                          '.spreadsheetml.sheet',
        })
 
        # ── Retour action téléchargement ──────────────────────────────────────
        return {
            'type':   'ir.actions.act_url',
            'url':    f'/web/content/{attach.id}?download=true',
            'target': 'self',
        }


class ProductCatalogueReport(models.AbstractModel):
    _name = 'report.custom_reports.report_product_template'
    _description = 'Catalogue Articles QWeb'

    def _get_report_values(self, docids, data=None):

        products = self.env['product.template'].browse(docids)

        categ_dict = defaultdict(list)

        for p in products:

            categ_id = p.categ_id.id if p.categ_id else 0

            categ_dict[categ_id].append(p)   # ✅ on garde le record

        docs_by_categ = []

        for categ_id, prods in sorted(categ_dict.items()):

            categ = self.env['product.category'].browse(categ_id)

            docs_by_categ.append({
                'categ_id': categ.code if categ else False,
                'categ_name': categ.name if categ else 'Sans catégorie',
                'products': prods
            })

        return {
            'doc_ids': docids,
            'doc_model': 'product.template',
            'docs_by_categ': docs_by_categ,
            'docs': products,
            'res_company': self.env.company,
            'today': datetime.date.today(),
        }
