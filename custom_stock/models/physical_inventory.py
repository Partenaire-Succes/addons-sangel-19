# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaire Succes Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com>)
#    Author: Adama KONE
#
#############################################################################
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PhysicalInventory(models.Model):
    _name = 'physical.inventory'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Physical Inventory'

    name = fields.Char(string='Nom', required=True, copy=False)
    code_inventory_id = fields.Many2many('code.inventory', string='Code Inventaire', copy=True)
    code_category_id = fields.Many2one('code.category.inventory', string='Categorie Code Inventaire', copy=True)
    team_inventory_id = fields.Many2one('team.inventory', string='Equipe', copy=True)
    inventory_mode = fields.Selection([
            ('normal', 'Inventaire'),
            ('verification_carryover', 'Produits à vérifier')
        ], string='Mode d\'inventaire', default='normal', required=True)
    state = fields.Selection([
            ('draft', 'Compatage'), 
            ('in_progress', 'Verification'), 
            ('done', 'Terminé')
        ], string='État', default='draft', required=True)
    line_quant_ids = fields.One2many(
        'stock.quant', 
        'inventory_physical_id', 
        string='Lignes d\'inventaire', 
        compute = 'get_products_quants',
        readonly=False,
        copy=True)
    physical_line_ids = fields.One2many(
        'physical.inventory.line', 
        'inventory_physical_id', 
        string='Lignes d\'inventaire', 
        readonly=False,
        copy=True)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company, readonly=True)
    date = fields.Datetime(string="Date de l'inventaire", default=fields.Datetime.now, required=True, copy=False)
    date_done = fields.Datetime(string='Date de fin', copy=False, readonly=True)
    is_negative_stock = fields.Boolean(string='Stock Negatif', default=False)
    note = fields.Text('Note')
    unverified_product_count = fields.Integer(string='Produits à vérifier', compute='_compute_unverified_product_count', store=True)

    physical_achive_line_ids = fields.One2many(
        comodel_name="physical.inventory.line.archive",
        inverse_name='inventory_physical_id',
        string="A vérifier"
    )


    def action_done(self):
        self.write({'state': 'done', 'date_done': fields.Datetime.now()})

    def action_draft(self):
        self.write({'state': 'draft', 'date_done': False})

    def action_start(self):
        if not self.physical_line_ids:
            raise UserError(_("Vous devez d'abord créer les lignes d'inventaire physique."))
        self.write({'state': 'in_progress'})

    @api.constrains('inventory_mode', 'code_inventory_id', 'code_category_id', 'team_inventory_id')
    def _check_required_fields_for_normal_mode(self):
        """Validate that required fields are set based on inventory mode"""
        for record in self:
            if record.inventory_mode == 'normal':
                if not record.code_inventory_id:
                    raise UserError(_("Au moins un 'Code Inventaire' est obligatoire en mode 'Inventaire'."))
                if not record.code_category_id:
                    raise UserError(_("La 'Categorie Code Inventaire' est obligatoire en mode 'Inventaire'."))
                if not record.team_inventory_id:
                    raise UserError(_("L'équipe est obligatoire en mode 'Inventaire'."))

    @api.depends('date', 'company_id')
    def _compute_unverified_product_count(self):
        """Compute count of unverified products from previous inventory sessions"""
        for record in self:
            if record.inventory_mode == 'verification_carryover':
                unverified_products = self.env['physical.inventory.line.archive'].search([
                #    ('archived_date', '<=', record.date),
                    ('inventory_physical_id.company_id', '=', record.company_id.id),
                    ('needs_verification', '=', True),
                ])
                record.unverified_product_count = len(unverified_products)
            else:
                record.unverified_product_count = 0

    def _get_unverified_products_from_previous_sessions(self):
        """Get list of unverified products from previous inventory sessions"""
        self.ensure_one()
        
        # Find all archived lines marked as needs_verification from previous sessions
        # Use strictly less-than (<) to exclude current session, only get from previous sessions
        unverified_archives = self.env['physical.inventory.line.archive'].search([
        #    ('archived_date', '<=', self.date),
            ('inventory_physical_id.company_id', '=', self.company_id.id),
            ('needs_verification', '=', True),
        ], order='product_tmpl_id,inventory_physical_id DESC')
        
        # Group by product to avoid duplicates (take latest archive per product)
        product_dict = {}
        for archive in unverified_archives:
            if archive.product_id.id not in product_dict:
                product_dict[archive.product_id.id] = archive
        
        return product_dict.values()


    @api.onchange('code_inventory_id')
    def get_products_quants(self):
        quants = self.env['stock.quant']
        domain = [
            ('location_id.usage', 'in', ['internal', 'transit']),
            ('product_id.active', '=', True),
        ]

        if self.code_inventory_id:
            domain.append(('code_inventory_id', 'in', self.code_inventory_id.ids))
        quants = quants.search(domain)
        self.line_quant_ids = [(6, 0, quants.ids)]

    def unlink(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_("Vous ne pouvez supprimer que les inventaires à l'état Brouillon."))
        return super(PhysicalInventory, self).unlink()
    
    
    def create_line_physical(self):
        """Generate physical inventory lines based on mode (normal or verification carryover)"""
        self.physical_line_ids.unlink()
        
        if self.inventory_mode == 'normal':
            # Normal mode: generate from stock quants
            for stck in self.line_quant_ids:
                self.env['physical.inventory.line'].create({
                    'inventory_physical_id': self.id,
                    'quant_id': stck.id,
                    'product_tmpl_id' : stck.product_tmpl_id.id,
                    'product_id' : stck.product_id.id,
                    'location_id' : stck.location_id.id,
                    'quantity' : stck.quantity,
                    'lot_id': stck.lot_id.id if stck.lot_id else False,
                    'product_uom_id': stck.product_uom_id.id,
                    'code_category_id': self.code_category_id.id,
                })
        else:
            # Verification carryover mode: generate from unverified products in previous sessions
            unverified_archives = self._get_unverified_products_from_previous_sessions()
            
            for archive in unverified_archives:
                self.env['physical.inventory.line'].create({
                    'inventory_physical_id': self.id,
                    'quant_id': archive.quant_id.id,
                    'product_tmpl_id': archive.product_tmpl_id.id,
                    'product_id': archive.product_id.id,
                    'location_id': archive.location_id.id,
                    'quantity': archive.quantity,
                    'lot_id': archive.lot_id.id if archive.lot_id else False,
                    'product_uom_id': archive.product_uom_id.id,
                    'code_category_id': archive.code_category_id.id,
                    'needs_verification': True,
                })


    def action_print_inventaire_report(self):
        """Méthode principale pour imprimer le rapport d'inventaire"""
        self.ensure_one()
        
        if not self.physical_line_ids:
            raise UserError("Impossible d'imprimer : aucune ligne d'inventaire trouvée.")
        
        filtered_lines = self._get_filtered_lines()
        self._log_print_action()
        
        return self.env.ref('custom_stock.action_report_physical_inventory').with_context(
            filtered_lines=filtered_lines.ids
        ).report_action(self)

    def action_print_inventaire_report_decompte(self):
        """Méthode principale pour imprimer le rapport d'inventaire"""
        self.ensure_one()

        if not self.physical_line_ids:
            raise UserError("Impossible d'imprimer : aucune ligne d'inventaire trouvée.")

        filtered_lines = self._get_filtered_lines()
        self._log_print_action()

        return self.env.ref('custom_stock.action_report_physical_inventory_decompte').with_context(
            filtered_lines=filtered_lines.ids
        ).report_action(self)


    def _get_filtered_lines(self):
        """Méthode pour filtrer les lignes selon vos critères"""
        lines = self.physical_line_ids        
        if self.is_negative_stock:
            lines = lines.filtered(lambda l: l.qty_diff < 0)        
        return lines

    def _log_print_action(self):
        """Enregistrer l'action d'impression dans le chatter"""
        self.message_post(
            body=f"Rapport d'inventaire imprimé par {self.env.user.name}",
            subject="Impression rapport d'inventaire",
            message_type='notification'
        )


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    inventory_physical_id = fields.Many2one('physical.inventory', string='Inventaire Physique', copy=True)
    code_category_id = fields.Many2one('code.category.inventory', string='Categorie Code Inventaire', copy=True)
    code_inventory_id = fields.Many2one(
        'code.inventory', 
        string='Code Inventaire', 
        related='product_tmpl_id.code_inventory_id',
        required=True)


class PhysicalInventoryLine(models.Model):
    _name = 'physical.inventory.line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Physical Inventory line'

    active = fields.Boolean('Actif', default=True, tracking=True)
    needs_verification = fields.Boolean('À vérifier', default=False, help='Marquer comme produit à vérifier dans la session suivante')

    quant_id = fields.Many2one(
        'stock.quant',
        'Stock'
    )
    state = fields.Selection(related='inventory_physical_id.state', string='État')
    product_tmpl_id = fields.Many2one(
        'product.template',
        'Produit'
    )
    product_id = fields.Many2one(
        'product.product',
        'Produits'
    )
    location_id = fields.Many2one(
        'stock.location',
        'Emplacement'
    )
    quantity = fields.Float('Stock')
    product_uom_id = fields.Many2one('uom.uom', "Unite", related="product_id.uom_id", readonly=True)

    physical_qty = fields.Float('Qte compté', default=0)
    qty_diff = fields.Float('Difference', compute="compute_qty_dif")
    valorisation = fields.Float('Valorisation', compute="compute_qty_dif")
    standard_price = fields.Float('Prix standard', related='product_tmpl_id.standard_price', readonly=True)

    inventory_physical_id = fields.Many2one('physical.inventory', string='Inventaire Physique', copy=True)
    code_category_id = fields.Many2one('code.category.inventory', string='Categorie Code Inventaire', copy=True)
    code_inventory_id = fields.Many2one(
        'code.inventory', 
        string='Code Inventaire', 
        related='product_tmpl_id.code_inventory_id',
        required=True)

    lot_id = fields.Many2one('stock.lot', string='Numéro de Lot', domain="[('product_id', '=', product_id)]")
    company_id = fields.Many2one('res.company', string='Société', related='inventory_physical_id.company_id')
    code_article = fields.Char(string='Code Article', related='product_tmpl_id.code_article')

    @api.onchange('physical_qty')
    def compute_qty_dif(self):
        for qt in self:
            qt.qty_diff = qt.physical_qty - qt.quantity
            qt.valorisation = qt.standard_price * qt.qty_diff

    def action_archive_line(self):
        """Archive la ligne et marque comme à vérifier si applicable"""
        self.ensure_one()

        # Création de l'enregistrement archive
        # Automatically mark as needs_verification=True when archiving
        # because archived lines need to be verified in a future session
        archive_vals = {
            'original_line_id': self.id,
            'quant_id': self.quant_id.id,
            'product_tmpl_id': self.product_tmpl_id.id,
            'product_id': self.product_id.id,
            'location_id': self.location_id.id,
            'quantity': self.quantity,
            'physical_qty': self.physical_qty,
            'qty_diff': self.qty_diff,
            'valorisation': self.valorisation,
            'standard_price': self.standard_price,
            'inventory_physical_id': self.inventory_physical_id.id,
            'code_category_id': self.code_category_id.id,
            'lot_id': self.lot_id.id if self.lot_id else False,
            'company_id': self.company_id.id,
            'archived_date': fields.Datetime.now(),
            'archived_by': self.env.user.id,
            'needs_verification': True,
        }

        self.env['physical.inventory.line.archive'].create(archive_vals)

        # Archiver la ligne
        self.write({'active': False})

        # Afficher notification et recharger le parent (vue form)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Archivé",
                "message": "La ligne a été retirée avec succès.",
                "type": "success",
                "sticky": False,
            },
        }, {
            "type": "ir.actions.act_window_view_reload"
        }


class PhysicalInventoryLineArchive(models.Model):
    """Modèle pour stocker les lignes d'inventaire archivées"""
    _name = 'physical.inventory.line.archive'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Physical Inventory Line Archive'
    _rec_name = 'product_tmpl_id'

    original_line_id = fields.Many2one('physical.inventory.line', string='Ligne originale', ondelete='set null')
    needs_verification = fields.Boolean('À vérifier', default=False, help='Produit marqué comme à vérifier pour session ultérieure')

    quant_id = fields.Many2one('stock.quant', 'Stock')
    product_tmpl_id = fields.Many2one('product.template', 'Produit', required=True)
    product_id = fields.Many2one('product.product', 'Produits', required=True)
    location_id = fields.Many2one('stock.location', 'Emplacement')
    quantity = fields.Float('Stock')
    product_uom_id = fields.Many2one('uom.uom', "Unite", related="product_id.uom_id", readonly=True)

    physical_qty = fields.Float('Qte compté')
    qty_diff = fields.Float('Difference')
    valorisation = fields.Float('Valorisation')
    standard_price = fields.Float('Prix standard')

    inventory_physical_id = fields.Many2one('physical.inventory', string='Inventaire Physique')
    code_category_id = fields.Many2one('code.category.inventory', string='Categorie Code Inventaire')
    code_inventory_id = fields.Many2one('code.inventory', string='Code Inventaire',
                                        related='product_tmpl_id.code_inventory_id')

    lot_id = fields.Many2one('stock.lot', string='Numéro de Lot')
    company_id = fields.Many2one('res.company', string='Société')
    code_article = fields.Char(string='Code Article', related='product_tmpl_id.code_article')

    # Informations d'archivage
    archived_date = fields.Datetime('Date d\'archivage', required=True, readonly=True, tracking=True)
    archived_by = fields.Many2one('res.users', string='Archivé par', required=True, readonly=True, tracking=True)
    archive_reason = fields.Text('Raison de l\'archivage', tracking=True)

    def action_restore_line(self):
        """Restaurer la ligne archivée"""
        self.ensure_one()

        if self.original_line_id:
            # Réactiver la ligne originale
            self.original_line_id.write({'active': True})

            # Supprimer l'enregistrement d'archive
            self.unlink()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Restauré',
                    'message': 'La ligne a été restaurée avec succès.',
                    'type': 'success',
                    'sticky': False,
                }
            },{
            "type": "ir.actions.act_window_view_reload"
             }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Erreur',
                    'message': 'Impossible de restaurer : ligne originale introuvable.',
                    'type': 'warning',
                    'sticky': False,
                }
            },{
            "type": "ir.actions.act_window_view_reload"
            }
