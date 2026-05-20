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

# ── Seuil pour détecter un coût AVCO aberrant avant/après ajustement ─────────
_AVCO_MAX_PLAUSIBLE = 10_000_000   # 10 millions FCFA max par unité
_AVCO_QTY_EPSILON   = 1e-6


class PhysicalInventory(models.Model):
    _name = 'physical.inventory'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Physical Inventory'
    _order = 'create_date desc'

    name = fields.Char(string='Nom', required=True, copy=False)
    code_inventory_id = fields.Many2many('code.inventory', string='Code Inventaire', copy=True)
    code_category_id = fields.Many2one('code.category.inventory', string='Categorie Code Inventaire', copy=True)
    team_inventory_id = fields.Many2one('team.inventory', string='Equipe', copy=True)
    inventory_mode = fields.Selection([
            ('normal', 'Inventaire'),
            ('libre', 'Libre'),
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


    # def action_done(self):
    #     self.write({'state': 'done', 'date_done': fields.Datetime.now()})
    #     for line in self.physical_line_ids.filtered(lambda l: l.active):
    #         line.product_tmpl_id.write({'qty_available': line.physical_qty})

    def action_done(self):
        """
        Valide l'inventaire physique en appliquant les ajustements de stock
        via le mécanisme NATIF Odoo (stock.quant._apply_inventory).
        """
        self.ensure_one()

        self.write({'state': 'done', 'date_done': fields.Datetime.now()})

        active_lines = self.physical_line_ids.filtered(lambda l: l.active)
        if not active_lines:
            return

        # Regrouper les ajustements par quant pour les appliquer en batch
        quants_to_apply = self.env['stock.quant']

        for line in active_lines:
            quant = line.quant_id

            # ── Si le quant de référence n'existe plus, le retrouver/créer ──
            if not quant or not quant.exists():
                quant = self.env['stock.quant'].search([
                    ('product_id',  '=', line.product_id.id),
                    ('location_id', '=', line.location_id.id),
                    ('lot_id',      '=', line.lot_id.id if line.lot_id else False),
                ], limit=1)

            if quant:
                # ── Fixer la quantité comptée via inventory_mode ─────────────
                # inventory_quantity = quantité physiquement comptée
                # inventory_diff_quantity = inventory_quantity - quantity (auto)
                # _apply_inventory() crée le stock.move pour l'écart
                quant.with_context(inventory_mode=True).write({
                    'inventory_quantity': line.physical_qty,
                })
                quants_to_apply |= quant
            else:
                # ── Quant inexistant : créer via inventory_mode ──────────────
                # Odoo crée le quant ET le stock.move d'ajustement
                if line.physical_qty:
                    new_quant = self.env['stock.quant'].with_context(
                        inventory_mode=True
                    ).create({
                        'product_id':   line.product_id.id,
                        'location_id':  line.location_id.id,
                        'lot_id':       line.lot_id.id if line.lot_id else False,
                        'inventory_quantity': line.physical_qty,
                    })
                    quants_to_apply |= new_quant

        # ── Appliquer tous les ajustements en une seule passe ─────────────────
        # Crée les stock.move (is_inventory=True) et les valide
        # Le nom de l'inventaire est passé via le contexte pour la traçabilité
        if quants_to_apply:
            quants_to_apply.with_context(
                inventory_mode=False,
                inventory_name=self.name,   # apparaît dans le libellé du mouvement
            )._apply_inventory(date=self.date)

        # ── Vérification post-ajustement : détecter les AVCO aberrants ────────
        self._check_avco_after_inventory(active_lines)

    def _check_avco_after_inventory(self, lines):
        """
        Vérifie après validation que l'AVCO des produits ajustés est cohérent.
        Si aberrant, log une alerte et notifie le canal stock.
        """
        aberrant = []
        for line in lines:
            if not line.product_id:
                continue
            cost = line.product_id.product_tmpl_id.standard_price
            if cost < 0 or cost > _AVCO_MAX_PLAUSIBLE:
                aberrant.append(
                    f"[{line.product_id.default_code or '?'}] "
                    f"{line.product_id.name} → {cost:,.0f} FCFA"
                )

        if aberrant:
            msg = (
                "🚨 <b>AVCO aberrant détecté après validation de l'inventaire</b><br/>"
                f"Inventaire : <b>{self.name}</b><br/>"
                "Produits concernés :<br/>"
                + "<br/>".join(f"• {p}" for p in aberrant)
                + "<br/><b>Action requise : corriger le coût via Inventaire → "
                "Fiche article → Mettre à jour le coût</b>"
            )
            self.message_post(body=msg, message_type='notification')

    def action_draft(self):
        self.write({'state': 'draft', 'date_done': False})

    def action_start(self):
        for rec in self:
            if not rec.physical_line_ids:
                raise UserError(
                    _("Vous devez d'abord créer les lignes d'inventaire physique.")
                )

        # Toutes les validations sont passées, on peut procéder
        for rec in self:
            if rec.inventory_mode == 'libre':
                for line in rec.physical_line_ids:
                    line.quantity = line.qty
                    line.price = line.standard_price
        self.write({'state': 'in_progress'})

    def update_price(self):
        lines = self.env['physical.inventory.line'].search([])
        for line in lines:
            if line.qty_diff:
                line.price = line.valorisation / line.qty_diff
            else:
                line.price = line.standard_price

    def action_refresh_qty_price(self):
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError(_("L'actualisation du stock et du prix n'est possible qu'en phase de Vérification."))
        for line in self.physical_line_ids.filtered(lambda l: l.active):
            quant = line.quant_id if line.quant_id and line.quant_id.exists() else False
            if not quant and line.product_id and line.location_id:
                quant = self.env['stock.quant'].search([
                    ('product_id',  '=', line.product_id.id),
                    ('location_id', '=', line.location_id.id),
                    ('lot_id',      '=', line.lot_id.id if line.lot_id else False),
                ], limit=1)
            if quant:
                line.quantity = quant.quantity
            line.price = line.product_tmpl_id.standard_price

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

        if self.inventory_mode == 'libre':
            for line in self.physical_line_ids:
                if line.code_category_id:
                    self.code_inventory_id = [(4, line.code_category_id.id)]
                    line.quantity = line.qty
                    line.price = line.standard_price
            return

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
                    'price': stck.product_tmpl_id.standard_price,
                    'lot_id': stck.lot_id.id if stck.lot_id else False,
                    'product_uom_id': stck.product_uom_id.id,
                    'code_category_id': self.code_category_id.id,
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
        lines = self.physical_line_ids.filtered(lambda l: l.active)    
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

    quant_id = fields.Many2one(
        'stock.quant',
        'Stock'
    )
    state = fields.Selection(related='inventory_physical_id.state', string='État')
    inventory_mode = fields.Selection(related='inventory_physical_id.inventory_mode', string='Mode', store=False)
    product_tmpl_id = fields.Many2one(
        'product.template',
        'Produit'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Produit',
        compute='_compute_product_id',
        store=True
    )

    location_id = fields.Many2one(
        'stock.location',
        'Emplacement',
        default=lambda self: self.env['stock.location'].search([('usage', '=', 'internal')], limit=1)
    )
 
    product_uom_id = fields.Many2one('uom.uom', "Unite", related="product_id.uom_id", readonly=True)

    physical_qty = fields.Float('Qte compté', default=0)
    standard_price = fields.Float('Prix standard', related='product_tmpl_id.standard_price')
    price = fields.Float('Prix standard')
    qty = fields.Float('Stock', related='product_tmpl_id.qty_available')
    quantity = fields.Float('Stock')

    qty_diff      = fields.Float('Difference',   compute='compute_qty_dif', store=True)
    valorisation  = fields.Float('Valorisation', compute='compute_qty_dif', store=True)

    inventory_physical_id = fields.Many2one('physical.inventory', string='Inventaire Physique', copy=True)
    code_category_id = fields.Many2one('code.category.inventory', string='Categorie Code Inventaire', copy=True)
    code_inventory_id = fields.Many2one(
        'code.inventory', 
        string='Code Inventaire', 
        related='product_tmpl_id.code_inventory_id',
        required=True)
    verified_by_id = fields.Many2one('res.partner', string='Vérifié par', help='Contact qui a vérifié ce produit') 

    lot_id = fields.Many2one('stock.lot', string='Numéro de Lot', domain="[('product_id', '=', product_id)]")
    company_id = fields.Many2one('res.company', string='Société', related='inventory_physical_id.company_id')
    code_article = fields.Char(string='Code Article', related='product_tmpl_id.code_article')
                

    def unlink(self):
        for line in self:
            if line.inventory_physical_id and line.inventory_physical_id.inventory_mode == 'normal':
                raise UserError(
                    "La suppression de lignes n'est pas autorisée en mode Inventaire normal.\n"
                    "Merci de valider votre inventaire."
                )
        return super().unlink()

    @api.depends('physical_qty', 'quantity', 'price')
    def compute_qty_dif(self):
        for line in self:
            # Utiliser `quantity` (stock du quant) et non `qty` (qty_available)
            line.qty_diff    = line.physical_qty - line.quantity
            line.valorisation = line.price * line.qty_diff


    @api.depends('product_tmpl_id')
    def _compute_product_id(self):
        for line in self:
            line.product_id = line.product_tmpl_id.product_variant_id
            

    @api.onchange('product_id', 'location_id')
    def _onchange_quant(self):
        for line in self:
            if line.product_id and line.location_id:
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', line.location_id.id),
                ], limit=1)
                line.quant_id = quant
