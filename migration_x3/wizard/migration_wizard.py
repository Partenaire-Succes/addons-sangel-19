# -*- coding: utf-8 -*-
import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.migration_x3.models.x3_connector import SageX3Connector
from odoo.addons.migration_x3.models.x3_mapper import SageX3Mapper

_logger = logging.getLogger(__name__)


class MigrationWizard(models.TransientModel):
    """
    Wizard de pilotage de la migration Sage X3 → Odoo.
    Accessible depuis : Migration X3 > Lancer une migration
    """
    _name = 'x3.migration.wizard'
    _description = 'Wizard Migration Sage X3'

    # ── Config ────────────────────────────────────────────────────────────────
    config_id = fields.Many2one(
        'x3.config', string='Configuration X3',
        required=True,
        domain=[('state', '=', 'ok')]
    )

    # ── Sélection des objets à migrer ─────────────────────────────────────────
    migrate_plan_comptable  = fields.Boolean('Plan comptable', default=True)
    migrate_clients         = fields.Boolean('Clients', default=True)
    migrate_fournisseurs    = fields.Boolean('Fournisseurs', default=True)
    migrate_ecritures       = fields.Boolean('Écritures comptables', default=False)
    migrate_factures_ventes = fields.Boolean('Factures ventes ouvertes', default=False)
    migrate_factures_achats = fields.Boolean('Factures achats ouvertes', default=False)

    # ── Paramètres ────────────────────────────────────────────────────────────
    date_debut = fields.Date(
        string='Date début',
        help="Pour les écritures et factures"
    )
    date_fin = fields.Date(
        string='Date fin',
        help="Pour les écritures et factures"
    )
    mode = fields.Selection([
        ('preview',  '👁 Aperçu (sans import)'),
        ('import',   '🚀 Import réel'),
    ], string='Mode', default='preview', required=True)

    update_existing = fields.Boolean(
        string='Mettre à jour les existants',
        default=False,
        help="Si coché, met à jour les enregistrements déjà présents dans Odoo"
    )

    # ── Résultats ─────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',   'Prêt'),
        ('running', 'En cours...'),
        ('done',    'Terminé'),
    ], default='draft')

    result_summary = fields.Text(string='Résumé', readonly=True)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_run(self):
        """Lance la migration selon le mode choisi."""
        self.ensure_one()

        if not any([
            self.migrate_plan_comptable,
            self.migrate_clients,
            self.migrate_fournisseurs,
            self.migrate_ecritures,
            self.migrate_factures_ventes,
            self.migrate_factures_achats,
        ]):
            raise UserError(_("Sélectionne au moins un objet à migrer."))

        config = self.config_id
        connector = SageX3Connector(config)
        mapper = SageX3Mapper(self.env)

        summary = []
        self.state = 'running'

        # ── 1. Plan comptable ─────────────────────────────────────────────────
        if self.migrate_plan_comptable:
            _logger.info("[WIZARD] Migration plan comptable...")
            x3_data = connector.get_plan_comptable(config)
            mapped, errors = mapper.map_plan_comptable(x3_data)
            count = self._import_plan_comptable(mapped, errors, config)
            summary.append(f"✅ Plan comptable : {count['ok']} importés, "
                           f"{count['skip']} ignorés, {count['error']} erreurs")

        # ── 2. Clients ────────────────────────────────────────────────────────
        if self.migrate_clients:
            _logger.info("[WIZARD] Migration clients...")
            x3_data = connector.get_clients(config)
            mapped, errors = mapper.map_clients(x3_data)
            count = self._import_partners(mapped, errors, config, 'clients')
            summary.append(f"✅ Clients : {count['ok']} importés, "
                           f"{count['skip']} ignorés, {count['error']} erreurs")

        # ── 3. Fournisseurs ───────────────────────────────────────────────────
        if self.migrate_fournisseurs:
            _logger.info("[WIZARD] Migration fournisseurs...")
            x3_data = connector.get_fournisseurs(config)
            mapped, errors = mapper.map_fournisseurs(x3_data)
            count = self._import_partners(mapped, errors, config, 'fournisseurs')
            summary.append(f"✅ Fournisseurs : {count['ok']} importés, "
                           f"{count['skip']} ignorés, {count['error']} erreurs")

        # ── 4. Écritures ──────────────────────────────────────────────────────
        if self.migrate_ecritures:
            _logger.info("[WIZARD] Migration écritures comptables...")
            date_d = str(self.date_debut) if self.date_debut else None
            date_f = str(self.date_fin) if self.date_fin else None
            x3_data = connector.get_ecritures(config, date_d, date_f)
            mapped, errors = mapper.map_ecritures(x3_data)
            count = self._import_ecritures(mapped, errors, config)
            summary.append(f"✅ Écritures : {count['ok']} importées, "
                           f"{count['skip']} ignorées, {count['error']} erreurs")

        # ── 5. Factures ventes ────────────────────────────────────────────────
        if self.migrate_factures_ventes:
            _logger.info("[WIZARD] Migration factures ventes...")
            x3_data = connector.get_factures_ventes(config, statut='OPEN')
            summary.append(f"✅ Factures ventes : {len(x3_data)} récupérées "
                           f"(import à compléter)")

        # ── 6. Factures achats ────────────────────────────────────────────────
        if self.migrate_factures_achats:
            _logger.info("[WIZARD] Migration factures achats...")
            x3_data = connector.get_factures_achats(config, statut='OPEN')
            summary.append(f"✅ Factures achats : {len(x3_data)} récupérées "
                           f"(import à compléter)")

        self.result_summary = '\n'.join(summary)
        self.state = 'done'

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ── Méthodes d'import ─────────────────────────────────────────────────────

    def _import_plan_comptable(self, mapped_records, errors, config):
        """Import des comptes dans account.account."""
        count = {'ok': 0, 'skip': 0, 'error': len(errors)}
        company_id = self.env.company.id

        for vals in mapped_records:
            try:
                existing = self.env['account.account'].search([
                    ('code', '=', vals['code']),
                    ('company_id', '=', company_id)
                ], limit=1)

                if existing:
                    if self.update_existing and self.mode == 'import':
                        existing.write({'name': vals['name']})
                    count['skip'] += 1
                elif self.mode == 'import':
                    vals['company_id'] = company_id
                    self.env['account.account'].create(vals)
                    count['ok'] += 1
                else:
                    count['ok'] += 1  # mode preview

            except Exception as e:
                count['error'] += 1
                _logger.error(f"[WIZARD] Compte {vals.get('code')} : {e}")

        self._log(config, 'plan_comptable', len(mapped_records),
                  count['ok'], count['error'], errors)
        return count

    def _import_partners(self, mapped_records, errors, config, objet):
        """Import des tiers dans res.partner."""
        count = {'ok': 0, 'skip': 0, 'error': len(errors)}

        for vals in mapped_records:
            try:
                ref = vals.get('ref', '')
                existing = self.env['res.partner'].search([
                    ('ref', '=', ref)
                ], limit=1) if ref else False

                if existing:
                    if self.update_existing and self.mode == 'import':
                        # Ne pas écraser le rang si déjà client ET fournisseur
                        write_vals = {k: v for k, v in vals.items()
                                      if k not in ('customer_rank', 'supplier_rank')}
                        existing.write(write_vals)
                    count['skip'] += 1
                elif self.mode == 'import':
                    # Retirer les champs compte (nécessite résolution Many2one)
                    vals.pop('property_account_receivable_id', None)
                    vals.pop('property_account_payable_id', None)
                    self.env['res.partner'].create(vals)
                    count['ok'] += 1
                else:
                    count['ok'] += 1

            except Exception as e:
                count['error'] += 1
                _logger.error(f"[WIZARD] Tiers {vals.get('name')} : {e}")

        self._log(config, objet, len(mapped_records),
                  count['ok'], count['error'], errors)
        return count

    def _import_ecritures(self, mapped_records, errors, config):
        """Import des écritures dans account.move."""
        count = {'ok': 0, 'skip': 0, 'error': len(errors)}

        for vals in mapped_records:
            try:
                # Vérifier doublon sur la référence
                existing = self.env['account.move'].search([
                    ('ref', '=', vals['ref']),
                    ('move_type', '=', 'entry'),
                ], limit=1)

                if existing:
                    count['skip'] += 1
                    continue

                if self.mode == 'import':
                    move = self.env['account.move'].create(vals)
                    # Ne pas poster automatiquement → laisser l'utilisateur valider
                    count['ok'] += 1
                else:
                    count['ok'] += 1

            except Exception as e:
                count['error'] += 1
                _logger.error(f"[WIZARD] Écriture {vals.get('ref')} : {e}")

        self._log(config, 'ecritures', len(mapped_records),
                  count['ok'], count['error'], errors)
        return count

    def _log(self, config, objet, total, ok, errors_count, errors_detail):
        """Enregistre un log de migration."""
        state = 'success' if errors_count == 0 else (
            'partial' if ok > 0 else 'error'
        )
        details = json.dumps(
            [{'record': str(e.get('record', '')), 'error': e.get('error', '')}
             for e in errors_detail[:50]],  # Max 50 erreurs dans le log
            ensure_ascii=False, indent=2
        ) if errors_detail else ''

        self.env['x3.migration.log'].create({
            'config_id': config.id,
            'objet': objet,
            'state': state,
            'total_x3': total,
            'total_ok': ok,
            'total_errors': errors_count,
            'details': details,
        })
