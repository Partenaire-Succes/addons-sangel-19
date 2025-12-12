# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaire Succes Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com>)
#    Author: Adama KONE
#
#############################################################################
from odoo import api, fields, models, _


class TeamInventory(models.Model):
    _name = 'team.inventory'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Team Inventory'

    name = fields.Char(string='Nom', required=True, copy=False)
    responsible_id = fields.Many2one('hr.employee', string='Chef d\'equipe', required=True)
    member_ids = fields.Many2many(
        'hr.employee', 
        string='Membres de l\'équipe',
        help="Users assigned to this team.")
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company)
