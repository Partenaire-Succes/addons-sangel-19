# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaire Succes Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com>)
#    Author: Adama KONE
#
#############################################################################
from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    fne_certified = fields.Boolean(string="Certifiée FNE", default=False, readonly=True)
    fne_reference = fields.Char(string="Référence FNE", readonly=True)
    id_fne = fields.Char(string="ID FNE", readonly=True)
    fne_token = fields.Char(string="Lien de vérification FNE", readonly=True)
    fne_sticker_balance = fields.Integer(string="Stickers restants")
    fne_response_json = fields.Text(string="Réponse FNE JSON")

    def action_open_fne_link(self):
        self.ensure_one()
        fne_token = self.fne_token
        if not fne_token:
            raise UserError("Aucun lien FNE disponible pour cette facture.")
        return {
            'type': 'ir.actions.act_url',
            'url': fne_token,
            'target': 'new',
        }

    def action_open_fne_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'FNE Certification',
            'res_model': 'fne.certification.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'default_partner_id': self.partner_id.id,
            }
        }
    

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    fne_original_line_id = fields.Char(string="id article FNE", readonly=True)