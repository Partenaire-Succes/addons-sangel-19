# -*- coding: utf-8 -*-
from odoo import models, fields


class MigrationLog(models.Model):
    """Trace toutes les opérations de migration."""
    _name = 'x3.migration.log'
    _description = 'Log de migration X3'
    _order = 'create_date desc'

    config_id = fields.Many2one('x3.config', string='Configuration', ondelete='cascade')
    date = fields.Datetime(string='Date', default=fields.Datetime.now)

    objet = fields.Selection([
        ('plan_comptable',  'Plan comptable'),
        ('clients',         'Clients'),
        ('fournisseurs',    'Fournisseurs'),
        ('ecritures',       'Écritures comptables'),
        ('factures_ventes', 'Factures ventes'),
        ('factures_achats', 'Factures achats'),
    ], string='Objet migré')

    state = fields.Selection([
        ('success', 'Succès'),
        ('partial', 'Partiel'),
        ('error',   'Erreur'),
    ], string='Statut', default='success')

    total_x3     = fields.Integer(string='Total X3')
    total_ok     = fields.Integer(string='Importés avec succès')
    total_errors = fields.Integer(string='Erreurs')
    details      = fields.Text(string='Détails / Erreurs')

    def name_get(self):
        result = []
        for rec in self:
            name = f"[{rec.date}] {rec.objet} - {rec.state}"
            result.append((rec.id, name))
        return result
