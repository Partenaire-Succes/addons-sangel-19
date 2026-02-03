# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPickingSupplyRequest(models.Model):
    """This class inherits 'stock.picking' and adds required fields """
    _name = 'stock.picking.supply.request'
    _description = 'Demande de transfert inter-société'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char('Nom', required=True, default=lambda self: _('New'), readonly=True, copy=False, )
    partner_id = fields.Many2one('res.partner', string='Fournisseur', ondelete='cascade')
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        string='Magasin',
        help="Société à laquelle appartient le transfert inter-société")
    send_company_id = fields.Many2one(
        'res.company',
        required=True,
        string='Magasin qui Cède',
        help="Société à laquelle appartient le transfert inter-société")
    date_done = fields.Date('Date de réalisation', default=fields.Date.context_today, readonly=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Brouillon'),
            ('done', 'Envoyé'),
            ('cancel', 'Annulé'),
        ],
        string='State',
        default='draft'
    )
    supply_request_line_ids = fields.One2many(
        'stock.picking.supply.request.line',
        'supply_request_id',
    )
    picking_inter_id = fields.Many2one(
        'stock.picking.inter',
        string='Transfert inter-société',
        ondelete='cascade'
    )

    picking_type_id = fields.Many2one('stock.picking.type', string='Type Operation', compute='action_location',
                                      required=True, store=True)
    location_id = fields.Many2one('stock.location', string='Emplacement origine', compute='action_location',
                                  required=True, store=True)
    location_dest_id = fields.Many2one('stock.location', compute='action_location', store=True, required=True,
                                       string='Emplacement Destination')
    

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'Le nom doit être unique.')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Generate a unique name for new inter company transfer."""
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'Nouveau':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('stock.picking.supply.request') or 'Nouveau'
        return super(StockPickingSupplyRequest, self).create(vals_list)


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
        """Confirmer la demande de transfert inter-société et créer les pickings associés"""
        for picking in self:
            if not picking.supply_request_line_ids:
                raise UserError(_("Veuillez ajouter au moins une ligne de transfert."))

            inter_lines = []

            for line in picking.supply_request_line_ids:
                if not line.product_id:
                    raise UserError(_("Veuillez sélectionner un produit pour la ligne de transfert."))
                if line.product_uom_qty <= 0:
                    raise UserError(
                        _("La quantité demandée doit être supérieure à zéro pour le produit %s.") % line.product_id.name)
                
                # Stock move pour le picking entrant
                inter_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                }))

            # Création du picking entrant avec le contexte de la société destinataire
            inter_vals = {
                'source': picking.name,
                'supply_request_id': picking.id,
                'partner_id': picking.send_company_id.partner_id.id,
                'company_id': picking.company_id.id,
                'send_company_id': picking.send_company_id.id,
                'scheduled_date': picking.date_done,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'picking_type_id': picking.picking_type_id.id,
                'picking_inter_line_ids': inter_lines,
            }

            # IMPORTANT: Utiliser sudo() avec le contexte de la société cible
            inter_picking = self.env['stock.picking.inter'].sudo().with_context(
                allowed_company_ids=[picking.send_company_id.id],
                force_company=picking.send_company_id.id
            ).search([
                ('source', '=', picking.name),
                ('company_id', '=', picking.company_id.id)
            ])

            if inter_picking:
                inter_picking.write(inter_vals)
            else:
                inter_picking = self.env['stock.picking.inter'].sudo().with_context(
                    allowed_company_ids=[picking.company_id.id],
                    force_company=picking.company_id.id
                ).create(inter_vals)

            picking.write({'state': 'done', 'picking_inter_id': inter_picking.id})

    def action_cancel_inter(self):
        """Annuler la demande de transfert inter-société et les pickings associés"""
        for picking in self:
            if picking.picking_inter_id:
                picking.picking_inter_id.action_cancel()
            picking.state = 'cancel'


    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Vous ne pouvez pas supprimer cette ligne sauf si l'état est brouillon.")
        return super().unlink()


class StockPickingSupplyRequestLine(models.Model):
    """
       Demande de transfert inter-société Ligne
    """
    _name = 'stock.picking.supply.request.line'
    _description = 'Demande de transfert inter-société Ligne'

    
    product_id = fields.Many2one('product.product', string='Produits')
    product_uom_qty = fields.Float('Demande')
    qty_available = fields.Float('En stock', related='product_id.qty_available', readonly=True)
    supply_request_id = fields.Many2one('stock.picking.supply.request', string='Demande de transfert inter-société')
    

    def unlink(self):
        for rec in self:
            if rec.supply_request_id.state != 'draft':
                raise UserError("Vous ne pouvez pas supprimer cette ligne sauf si l'état est brouillon.")
        return super().unlink()