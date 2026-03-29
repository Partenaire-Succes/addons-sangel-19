# -*- coding: utf-8 -*-
from datetime import datetime, time
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class RapportRetoursReceptionsWizard(models.TransientModel):
    """
    Wizard de génération du rapport consolidé Retours & Réceptions.

    Permet de filtrer par type (retours / réceptions / tout), plage de dates
    et fournisseur avant de télécharger le rapport PDF.
    Bonne pratique : l'utilisateur filtre d'abord, télécharge ensuite.
    """
    _name = 'rapport.retours.receptions.wizard'
    _description = 'Rapport Retours et Réceptions consolidé'

    # ── Filtre principal ─────────────────────────────────────────────────────
    type_rapport = fields.Selection([
        ('retours',    'Retours fournisseurs uniquement'),
        ('receptions', 'Réceptions directes uniquement'),
        ('tous',       'Tout (Retours + Réceptions)'),
    ], string='Contenu du rapport', default='tous', required=True)

    # ── Filtres secondaires ──────────────────────────────────────────────────
    date_debut = fields.Date(string='Date début')
    date_fin   = fields.Date(string='Date fin', default=fields.Date.today)
    partner_id = fields.Many2one(
        'res.partner',
        string='Fournisseur',
        domain=[('supplier_rank', '>', 0)],
        help="Laisser vide pour inclure tous les fournisseurs.",
    )

    # ── Helpers domaine ──────────────────────────────────────────────────────
    def _clauses_communes(self):
        """Clauses de filtre partagées (dates + fournisseur)."""
        clauses = []
        if self.date_debut:
            clauses.append(('scheduled_date', '>=',
                            datetime.combine(self.date_debut, time.min)))
        if self.date_fin:
            clauses.append(('scheduled_date', '<=',
                            datetime.combine(self.date_fin, time.max)))
        if self.partner_id:
            clauses.append(('partner_id', '=', self.partner_id.id))
        return clauses

    # ── Accesseurs données ───────────────────────────────────────────────────
    def get_retours(self):
        """Retours fournisseurs filtrés (pickings stock → fournisseur)."""
        if self.type_rapport not in ('retours', 'tous'):
            return self.env['stock.picking']
        domain = [
            ('location_dest_id.usage', '=', 'supplier'),
            ('picking_type_code', '=', 'incoming'),
        ] + self._clauses_communes()
        return self.env['stock.picking'].search(domain, order='scheduled_date desc')

    def get_receptions(self):
        """Réceptions directes filtrées (pickings créés via le wizard)."""
        if self.type_rapport not in ('receptions', 'tous'):
            return self.env['stock.picking']
        domain = [
            ('origin', '=', 'Réception Directe'),
            ('picking_type_code', '=', 'incoming'),
        ] + self._clauses_communes()
        return self.env['stock.picking'].search(domain, order='scheduled_date desc')

    def get_periode_label(self):
        """Label lisible de la période pour l'en-tête du rapport."""
        if self.date_debut and self.date_fin:
            return 'Du %s au %s' % (
                self.date_debut.strftime('%d/%m/%Y'),
                self.date_fin.strftime('%d/%m/%Y'),
            )
        if self.date_debut:
            return 'À partir du %s' % self.date_debut.strftime('%d/%m/%Y')
        if self.date_fin:
            return "Jusqu'au %s" % self.date_fin.strftime('%d/%m/%Y')
        return 'Toutes périodes'

    def get_type_label(self):
        """Label du type de rapport sélectionné."""
        labels = {
            'retours':    'Retours fournisseurs',
            'receptions': 'Réceptions directes',
            'tous':       'Retours + Réceptions',
        }
        return labels.get(self.type_rapport, '')

    def get_date_edition(self):
        """Date/heure d'édition formatée pour l'en-tête du rapport."""
        return fields.Datetime.now().strftime('%d/%m/%Y %H:%M')

    # ── Action principale ────────────────────────────────────────────────────
    def action_imprimer(self):
        """Génère et télécharge le rapport PDF consolidé."""
        self.ensure_one()
        retours    = self.get_retours()
        receptions = self.get_receptions()
        if not retours and not receptions:
            raise UserError(_(
                "Aucun mouvement trouvé pour les filtres sélectionnés.\n"
                "Essayez d'élargir la période ou de modifier le type de rapport."
            ))
        return self.env.ref(
            'custom_stock.action_report_retours_receptions'
        ).report_action(self)
