# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPickingInter(models.Model):
    """This class inherits 'stock.picking' and adds required fields """
    _name = 'stock.picking.inter'
    _description = 'Inter Company Stock Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char('Nom', required=True, default=lambda self: _('New'), readonly=True, copy=False, )
    picking_id = fields.Many2one('stock.picking', string='Stock', ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Fournisseur', ondelete='cascade')
    picking_type_id = fields.Many2one('stock.picking.type', string='Type Operation', compute='action_location',
                                      required=True, store=True)
    location_id = fields.Many2one('stock.location', string='Emplacement origine', compute='action_location',
                                  required=True, store=True)
    location_dest_id = fields.Many2one('stock.location', compute='action_location', store=True, required=True,
                                       string='Emplacement Destination')
    company_id = fields.Many2one(
        'res.company',
        required=True,
        string='Société qui reçoit',
        help="Société à laquelle appartient le transfert inter-société")
    send_company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        string='Recevoir de',
        help="Société à laquelle appartient le transfert inter-société")
    company_ids = fields.Many2many(
        'res.company',
        'company_tags_rel',
        'purchase_id',
        'company_id', string='Societe')

    scheduled_date = fields.Date('Date planifiée')
    date_done = fields.Date('Date du transfert')
    date_deadline = fields.Date('Date limite', required=False)
    current_date = fields.Date('Date du jour', default=lambda self: fields.Date.today())
    origin = fields.Char('Nom')
    state = fields.Selection(
        selection=[
            ('draft', 'Brouillon'),
            ('confirmed', 'Confirmé'),
            ('done', 'Fait'),
            ('cancel', 'Annulé'),
            ('reject', 'Rejeté')
        ],
        string='State',
        default='draft'
    )
    picking_inter_line_ids = fields.One2many(
        'stock.picking.inter.line',
        'picking_inter_id',
    )

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'Le nom doit être unique.')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Generate a unique name for new inter company transfer."""
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('stock.picking.inter') or 'Nouveau'
        return super(StockPickingInter, self).create(vals_list)

    @api.onchange('company_id')
    def action_location(self):
        """Confirm the inter-company transfer."""
        for picking in self:
            picking.picking_type_id = self.env['stock.picking.type'].with_context(force_company=False).sudo().search([
                ('code', '=', 'incoming'),
                ('company_id', '=', picking.company_id.id)
            ], limit=1)
            picking.location_id = self.env['stock.location'].with_context(force_company=False).sudo().search([
                ('usage', '=', 'customer'),
            ], limit=1)
            picking.location_dest_id = self.env['stock.location'].with_context(force_company=False).sudo().search([
                ('usage', '=', 'internal'),
                ('company_id', '=', picking.company_id.id)
            ], limit=1)

    def action_confirm_inter(self):
        """Confirme le transfert inter-société en créant un picking entrant avec lots et move lines."""
        for picking in self:
            if not picking.picking_type_id:
                raise UserError(_("Veuillez sélectionner un type d'opération."))
            if not picking.location_id:
                raise UserError(_("Veuillez sélectionner un emplacement d'origine."))
            if not picking.location_dest_id:
                raise UserError(_("Veuillez sélectionner un emplacement de destination."))
            if not picking.picking_inter_line_ids:
                raise UserError(_("Veuillez ajouter au moins une ligne de transfert."))
            if picking.date_deadline and picking.date_deadline < picking.current_date:
                raise UserError(_("La date limite ne peut pas être antérieure à la date du jour."))

            # Préparation du transfert sortant correspondant
            company_connect = picking.send_company_id
            picking_type_out = self.env['stock.picking.type'].with_context(force_company=False).sudo().search([
                ('code', '=', 'outgoing'),
                ('company_id', '=', company_connect.id)
            ], limit=1)
            location_dest_out = self.env['stock.location'].with_context(force_company=False).sudo().search([
                ('usage', '=', 'internal'),
                ('company_id', '=', company_connect.id)
            ], limit=1)

            _logger.info('picking_type_out: %s et location_dest_out : %s', picking_type_out.name,
                         location_dest_out.name)
            if not picking_type_out:
                raise UserError(_("Veuillez configurer un type de picking sortant pour la société sélectionnée."))
            if not location_dest_out:
                raise UserError(_("Veuillez configurer un emplacement de destination pour la société sélectionnée."))

            move_lines = []
            move_line_vals = []

            out_move_lines = []
            out_move_line_vals = []

            for line in picking.picking_inter_line_ids:
                if not line.product_id:
                    raise UserError(_("Veuillez sélectionner un produit pour la ligne de transfert."))
                if line.product_uom_qty <= 0:
                    raise UserError(
                        _("La quantité demandée doit être supérieure à zéro pour le produit %s.") % line.product_id.name)
                # line.product_id.product_tmpl_id.action_generate_lot(company_id=line.company_id.id)

                # Génération des lots
                # lots = self.env['stock.lot'].action_create_lot(
                #     product_id=line.product_id,
                #     company_id=line.company_id,
                #     qte=line.product_uom_qty,
                #     location_id=line.location_id
                # )
                #
                # out_lots = self.env['stock.lot'].action_create_lot(
                #     product_id=line.product_id,
                #     company_id=company_connect,
                #     qte=line.product_uom_qty,
                #     location_id=location_dest_out
                # )
                # Stock move
                move_lines.append((0, 0, {
                    'company_id': line.company_id.id,
                    'product_id': line.product_id.id,
                    'description_picking': line.description_picking or line.product_id.display_name,
                    'date': line.date,
                    'date_deadline': line.date_deadline,
                    'product_uom_qty': line.product_uom_qty,
                    'location_id': line.location_id.id,
                    'location_dest_id': line.location_dest_id.id,
                    'product_uom': line.product_id.uom_id.id,
                }))

                out_move_lines.append((0, 0, {
                    'company_id': company_connect.id,
                    'product_id': line.product_id.id,
                    'description_picking': line.description_picking or line.product_id.display_name,
                    'date': line.date,
                    'date_deadline': line.date_deadline,
                    'product_uom_qty': line.product_uom_qty,
                    'location_id': location_dest_out.id,
                    'location_dest_id': line.location_id.id,
                    'product_uom': line.product_id.uom_id.id,
                }))

                # Stock move lines (quantité réelle avec lot unitaire)
                # for lot in lots:
                #     move_line_vals.append((0, 0, {
                #         'product_id': line.product_id.id,
                #         'lot_id': lot.id,
                #         'lot_name': lot.name,
                #         'quantity': 1.0,
                #         'product_uom_id': line.product_id.uom_id.id,
                #         'location_id': line.location_id.id,
                #         'location_dest_id': line.location_dest_id.id,
                #     }))

                # for lot in out_lots:
                #     out_move_line_vals.append((0, 0, {
                #         'product_id': line.product_id.id,
                #         'lot_id': lot.id,
                #         'lot_name': lot.name,
                #         'quantity': 1.0,
                #         'product_uom_id': line.product_id.uom_id.id,
                #         'location_id': location_dest_out.id,
                #         'location_dest_id': line.location_id.id,
                #     }))

            # Création du picking entrant
            incoming_vals = {
                'name': picking.name,
                'picking_type_id': picking.picking_type_id.id,
                'partner_id': picking.partner_id.id,
                'company_id': picking.company_id.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'scheduled_date': picking.scheduled_date,
                'origin': picking.origin,
                'picking_type_code': 'incoming',
                'picking_inter_id': picking.id,
                'move_ids': move_lines,
                'move_line_ids': move_line_vals,
            }

            incoming_picking = self.env['stock.picking'].with_context(force_company=False).sudo().search([
                ('name', '=', picking.name),
                ('picking_type_code', '=', 'incoming'),
                ('company_id', '=', picking.company_id.id)
            ])

            if incoming_picking:
                incoming_picking.sudo().write(incoming_vals)
            else:
                incoming_picking = self.env['stock.picking'].sudo().create(incoming_vals)
                picking.write({'picking_id': incoming_picking.id})
                incoming_picking.action_confirm()

            # Copie pour créer le picking sortant

            outgoing_vals = {
                'name': f"{picking.name} - OUT",
                'picking_type_id': picking_type_out.id,
                'partner_id': picking.partner_id.id,
                'company_id': company_connect.id,
                'location_id': location_dest_out.id,
                'location_dest_id': picking.location_id.id,
                'scheduled_date': picking.scheduled_date,
                'origin': picking.origin,
                'picking_type_code': 'outgoing',
                'picking_inter_id': picking.id,
                'move_ids': out_move_lines,
                'move_line_ids': out_move_line_vals,
            }
            # Recherche du picking sortant existant ou création d'un nouveau
            outgoing_picking = self.env['stock.picking'].with_context(force_company=False).sudo().search([
                ('name', '=', f"{picking.name} - OUT"),
                ('picking_type_code', '=', 'outgoing'),
                ('company_id', '=', company_connect.id)
            ])

            if outgoing_picking:
                outgoing_picking = self.env['stock.picking'].sudo().update(outgoing_vals)
                outgoing_picking.write({
                    'state': 'assigned',
                })
            else:
                outgoing_picking = self.env['stock.picking'].sudo().create(outgoing_vals)
                outgoing_picking.action_confirm()

            # Mise à jour de l'état du picking inter-société
            picking.write({
                'state': 'confirmed',
            })

    def action_cancel(self):
        for inter in self:
            pickings = self.env['stock.picking'].with_context(force_company=False).sudo().search([
                ('picking_inter_id', '=', inter.id),
            ])
            if pickings:
                for picking in pickings:
                    if picking.state != 'done':
                        picking.action_cancel()
                        inter.write({'state': 'cancel'})
                    else:
                        raise UserError(
                            _("Le transfert inter-société ne peut pas être annulé car il est déjà terminé."))

    def action_open_wizard_add_product(self):
        view = self.env.ref('stock_intercompany.view_product_selector_form').id
        return {
            'name': _('Test Prod'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking.inter.wizard',
            'target': 'new',
            'views': [(view, 'form')],
            'context': {},
        }

    def action_draft(self):
        for inter in self:
            pickings = self.env['stock.picking'].with_context(force_company=False).sudo().search([
                ('picking_inter_id', '=', inter.id),
            ])
            if pickings:
                for picking in pickings:
                    if picking.state != 'done':
                        picking.unlink()
                        inter.write({'state': 'draft', })
                    else:
                        raise UserError(
                            _("Le transfert inter-société ne peut pas être remis à l'état brouillon car il est déjà terminé."))

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Vous ne pouvez pas supprimer cette ligne sauf si l'état est brouillon.")
        return super().unlink()


class StockPickingInterLine(models.Model):
    """This class inherits 'stock.picking' and adds required fields """
    _name = 'stock.picking.inter.line'
    _description = 'Inter Company Stock Transfer Line'

    company_id = fields.Many2one('res.company', string='Societe', related='picking_inter_id.company_id', store=True)
    picking_id = fields.Many2one('stock.picking', string='Stock')
    name = fields.Char('Nom')
    picking_type_id = fields.Many2one('stock.picking.type', string='Type Operation')
    location_id = fields.Many2one('stock.location', string='Emplacement origine',
                                  related='picking_inter_id.location_id')
    location_dest_id = fields.Many2one('stock.location', string='Emplacement Destination',
                                       related='picking_inter_id.location_dest_id')
    partner_id = fields.Many2one('res.partner', string='Recevoir de')
    move_line_ids = fields.One2many('stock.move.line', 'picking_inter_line_id', string='Ligne de mvt')
    product_id = fields.Many2one('product.product', string='Produits')
    description_picking = fields.Char('Description', related='product_id.name')
    date = fields.Date('Date planifiée', related='picking_inter_id.scheduled_date', readonly=False)
    date_deadline = fields.Date('Date limite')
    product_uom_qty = fields.Float('Demande')
    qty_available = fields.Float('En stock', related='product_id.qty_available', readonly=True)
    quantity = fields.Float('Quantité')
    move_id = fields.Many2one('stock.move', string='Mouvement')
    picking_inter_id = fields.Many2one('stock.picking.inter', string='Transfert inter-société')
    purchase_id = fields.Many2one('purchase.order',
                                  string='Achat lié',
                                  domain="[('order_line.product_id', '=', product_id)]")
    lot_ids = fields.Many2many(
        comodel_name='stock.lot',
        relation='stock_picking_inter_line_lot_rel',  # nom de la table relationnelle
        column1='picking_inter_line_id',  # champ qui relie à TON modèle
        column2='lot_id',  # champ qui relie à stock.lot
        string='Lots',
        help="Lots associés à ce transfert inter-société."
    )

    @api.onchange('product_id')
    def _onchange_product_id(self):
        self.purchase_id = False

    def unlink(self):
        for rec in self:
            if rec.picking_inter_id.state != 'draft':
                raise UserError("Vous ne pouvez pas supprimer cette ligne sauf si l'état est brouillon.")
        return super().unlink()



class StockMoveLineInherit(models.Model):
    """Inherits 'stock.move.line' and adds fields"""
    _inherit = 'stock.move.line'

    picking_inter_line_id = fields.Many2one('stock.picking.inter.line', string='Ligne de transfert inter-société')


class StockPickingInherit(models.Model):
    """Inherits 'stock.picking' and adds fields"""
    _inherit = 'stock.picking'

    picking_inter_id = fields.Many2one('stock.picking.inter', string='Transfert inter-société')

    def button_validate(self):
        res = super(StockPickingInherit, self).button_validate()
        for picking in self:
            if picking.picking_inter_id:
                picking.picking_inter_id.write({'state': 'done'})
        return res

    def action_cancel(self):
        res = super(StockPickingInherit, self).action_cancel()
        for picking in self:
            if picking.picking_inter_id:
                picking.picking_inter_id.write({'state': 'reject'})
        return res