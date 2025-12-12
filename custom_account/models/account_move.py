from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    def write(self, vals):
        """Trigger lors de la modification des factures"""
        res = super().write(vals)
        
        # Recalculer uniquement si les champs importants changent
        if any(key in vals for key in ['state', 'invoice_date', 'journal_id', 'line_ids', 'partner_id']):
            _logger.info(f"✏️ Modification de {len(self)} ligne(s) comptable(s)")
            for line in self.line_ids:
                line._trigger_daily_budget_recompute(line)
        
        return res


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    @api.model_create_multi
    def create(self, vals_list):
        """Trigger lors de la création de lignes comptables"""
        _logger.info(f"📝 Création de {len(vals_list)} ligne(s) comptable(s)")
        lines = super().create(vals_list)
        self._trigger_daily_budget_recompute(lines)
        return lines
    
    def unlink(self):
        """Trigger lors de la suppression de lignes comptables"""
        _logger.info(f"🗑️ Suppression de {len(self)} ligne(s) comptable(s)")
        self._trigger_daily_budget_recompute(self)
        return super().unlink()
    
    def _trigger_daily_budget_recompute(self, lines):
        """Recalcule les budgets journaliers concernés par les lignes comptables"""
        if not lines:
            return
        
        # Récupérer tous les comptes analytiques concernés
        analytic_ids = lines.mapped('distribution_analytic_account_ids').ids
        
        if not analytic_ids:
            _logger.debug("⏭️ Aucun compte analytique trouvé, skip recalcul")
            return
        
        # Trouver toutes les dates concernées
        dates = lines.mapped('date')
        if not dates:
            _logger.debug("⏭️ Aucune date trouvée, skip recalcul")
            return
        
        min_date = min(dates)
        max_date = max(dates)
        
        _logger.info(f"🔍 Recherche des budgets concernés")
        _logger.info(f"   Comptes analytiques: {analytic_ids}")
        _logger.info(f"   Période: {min_date} à {max_date}")
        
        # Chercher les lignes de budget journalier concernées
        BudgetLine = self.env['daily.budget.analytic.line'].sudo()
        
        budget_lines = BudgetLine.search([
            ('account_analytic_id', 'in', analytic_ids),
            ('date_from', '<=', max_date),
            ('date_to', '>=', min_date),
        ])
        
        _logger.info(f"📊 {len(budget_lines)} ligne(s) de budget trouvée(s)")
        
        # Forcer le recalcul
        if budget_lines:
            _logger.info(f"🔄 Recalcul du montant réel pour {len(budget_lines)} ligne(s)")
            budget_lines.compute_actual_amount()
            _logger.info(f"✅ Recalcul terminé")
        else:
            _logger.debug("⏭️ Aucune ligne de budget concernée")