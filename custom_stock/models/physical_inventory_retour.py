# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError


class PhysicalInventoryRetour(models.Model):
    """
    BLOC 4 — Ajout de l'action 'Générer un avoir' sur physical.inventory.
    Séparé du fichier principal pour ne pas modifier le code existant.
    """
    _inherit = 'physical.inventory'

    def action_open_retour_inventaire(self):
        """
        Ouvre le wizard de génération d'avoir/facture fournisseur.
        Pré-remplit automatiquement les lignes avec qty_diff < 0 (manquants).
        Accessible uniquement sur un inventaire terminé (state='done').
        """
        self.ensure_one()

        if self.state != 'done':
            raise UserError(_(
                "L'inventaire doit être à l'état 'Terminé' pour générer un document comptable."
            ))

        lignes_manquantes = self.physical_line_ids.filtered(
            lambda l: l.qty_diff < 0 and l.active
        )
        if not lignes_manquantes:
            raise UserError(_(
                "Aucun manquant détecté dans cet inventaire (toutes les différences sont ≥ 0).\n"
                "Le document comptable ne peut être généré que pour des écarts négatifs."
            ))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Générer un avoir / une facture fournisseur'),
            'res_model': 'retour.inventaire.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_inventory_id': self.id,
            },
        }
