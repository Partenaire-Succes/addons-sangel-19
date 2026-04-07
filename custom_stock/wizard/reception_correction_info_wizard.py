# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class ReceptionCorrectionInfoWizard(models.TransientModel):
    """
    Wizard de modification des informations non-stock d'une réception validée.

    N'impacte PAS les mouvements de stock ni la comptabilité.
    Modifiable uniquement : ref_sage, note, partner_id, scheduled_date.
    Toute modification est tracée dans le chatter du picking.
    """
    _name = 'reception.correction.info.wizard'
    _description = 'Modifier les informations de la réception (sans impact stock)'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Réception',
        required=True,
        readonly=True,
    )
    # Champs modifiables
    ref_sage = fields.Char(string='Réf. Cession / Sage')
    note = fields.Char(string='Référence / Notes')
    partner_id = fields.Many2one(
        'res.partner',
        string='Fournisseur',
        options="{'no_create': True, 'no_create_edit': True}",
    )
    scheduled_date = fields.Datetime(string='Date de réception')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking_id = (
            self.env.context.get('active_id')
            or self.env.context.get('default_picking_id')
        )
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            if picking.exists():
                res.update({
                    'picking_id': picking.id,
                    'ref_sage': picking.ref_sage or '',
                    'note': picking.note or '',
                    'partner_id': picking.partner_id.id if picking.partner_id else False,
                    'scheduled_date': picking.scheduled_date,
                })
        return res

    def action_appliquer(self):
        self.ensure_one()
        picking = self.picking_id

        if picking.state != 'done':
            raise UserError(_(
                "Ce bon de réception n'est pas encore validé. "
                "Utilisez la vue standard pour le modifier."
            ))

        # Construire le journal des modifications pour le chatter
        changes = []
        if (self.ref_sage or '') != (picking.ref_sage or ''):
            changes.append(
                'Réf. Cession/Sage : <i>%s</i> → <b>%s</b>'
                % (picking.ref_sage or '—', self.ref_sage or '—')
            )
        if (self.note or '') != (picking.note or ''):
            changes.append(
                'Notes : <i>%s</i> → <b>%s</b>'
                % (picking.note or '—', self.note or '—')
            )
        if self.partner_id != picking.partner_id:
            changes.append(
                'Fournisseur : <i>%s</i> → <b>%s</b>'
                % (picking.partner_id.name or '—', self.partner_id.name or '—')
            )
        if self.scheduled_date != picking.scheduled_date:
            fmt = '%d/%m/%Y %H:%M'
            changes.append(
                'Date : <i>%s</i> → <b>%s</b>' % (
                    picking.scheduled_date.strftime(fmt) if picking.scheduled_date else '—',
                    self.scheduled_date.strftime(fmt) if self.scheduled_date else '—',
                )
            )

        if not changes:
            raise UserError(_("Aucune modification détectée."))

        # Écriture (sudo pour contourner readonly UI sur ref_sage)
        picking.sudo().write({
            'ref_sage': self.ref_sage or '',
            'note': self.note or '',
            'partner_id': self.partner_id.id if self.partner_id else False,
            'scheduled_date': self.scheduled_date,
        })

        # Traçabilité chatter
        body = _(
            '<p><b>Informations modifiées</b> (sans impact stock)</p><ul>%s</ul>'
        ) % ''.join('<li>%s</li>' % c for c in changes)
        picking.message_post(body=body, message_type='notification')

        _logger.info(
            "[CORRECTION_INFO] Picking %s modifié par %s — %s changement(s)",
            picking.name, self.env.user.name, len(changes),
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Informations mises à jour'),
                'message': _('Les informations du bon %s ont été modifiées avec succès.') % picking.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
