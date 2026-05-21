from odoo import models, api, fields, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    mode_payment = fields.Selection([
            ('credit', 'Credit'), 
            ('cash', 'Cash'),
        ], string='Clients à compte', default='cash')
    is_limit = fields.Boolean('Limite Credit')

    def write(self, vals):
        """Trigger lors de la modification des factures"""
        res = super().write(vals)
        
        # Recalculer uniquement si les champs importants changent
        if any(key in vals for key in ['state', 'invoice_date', 'journal_id', 'line_ids', 'partner_id']):
            _logger.info(f"✏️ Modification de {len(self)} ligne(s) comptable(s)")
            for line in self.line_ids:
                line._trigger_daily_budget_recompute(line)
        
        return res
    

    def _get_unbalanced_moves(self, container):
        result = super()._get_unbalanced_moves(container)
        if not result:
            return result

        remaining = []
        for row in result:
            move_id = row[0]
            move = self.browse(move_id)

            if not move.pos_order_ids:
                remaining.append(row)
                continue

            delta = sum(line.balance for line in move.line_ids)
            delta_rounded = move.currency_id.round(delta)

            if not delta_rounded or abs(delta_rounded) > 5:
                remaining.append(row)
                continue

            tax_lines = move.line_ids.filtered(lambda l: l.tax_line_id)
            if not tax_lines:
                remaining.append(row)
                continue

            biggest = max(tax_lines, key=lambda l: abs(l.balance))
            new_balance = biggest.balance - delta_rounded
            new_debit = max(0.0, new_balance)
            new_credit = max(0.0, -new_balance)

            self.env.cr.execute(
                "UPDATE account_move_line SET balance=%s, amount_currency=%s, debit=%s, credit=%s WHERE id=%s",
                [new_balance, new_balance, new_debit, new_credit, biggest.id]
            )
            move.line_ids.invalidate_recordset(['balance', 'amount_currency', 'debit', 'credit'])
            _logger.info(
                "POS INVOICE: équilibrage automatique (delta=%s) sur facture %s, ligne '%s': %s -> %s",
                delta_rounded, move.pos_order_ids[:1].name, biggest.name or '?',
                biggest.balance + delta_rounded, new_balance
            )

        return remaining

    def _check_credit_limit(self):
        for order in self:
            if order.mode_payment == 'credit':
                if not order.partner_id.is_limit:
                    raise ValidationError(_("Le client %s n'a pas de limite crédit attribué.") 
                                        %  order.partner_id.name)

                limit_credit = self.env['limit.credit'].sudo().search([
                    ('partner_id', '=', order.partner_id.id),
                ], limit=1)

                if not limit_credit:
                    raise ValidationError(
                        _("Aucune limite crédit trouvé pour le client %s dans la période spécifiée.") 
                        % order.partner_id.name)

                solde_disponible = limit_credit.amount_limit - limit_credit.amount_limit_consumed
                _logger.info('Crédit disponible: %s', solde_disponible)

                if order.amount_total > solde_disponible:
                    raise ValidationError(
                        _("Le montant total de la commande (%s) dépasse la limite crédit disponible (%s) pour le client %s.") 
                        % (order.amount_total, solde_disponible, order.partner_id.name))

                # Mettre à jour amount_limit_consumed
                limit_credit.sudo().write({
                    'amount_limit_consumed': limit_credit.amount_limit_consumed + order.amount_total,
                })
                self.env['limit.credit.operation'].create({
                    'limit_id': limit_credit.id,
                    'name': "Gros & 1/2 Gros - %s - %s" % (order.name, order.company_id.lib_company),
                    'amount_operation': order.amount_total,
                    'operation_date': fields.Datetime.now(),
                })
                order.is_limit = True

                # Invalider tout le cache
                self.env.invalidate_all()
        return True


    def action_post(self):
        res = super(AccountMove, self).action_post()
        self._check_credit_limit()
        return res

    def button_draft(self):
        """Override to restore loyalty points when order is cancelled."""
        # Restore loyalty points before cancellation
        self._retire_credit_limit()
        return super().button_draft()
    

    def _retire_credit_limit(self):
        """Restore limit credit when order is cancelled."""
        for order in self:
            if order.mode_payment == 'credit' and order.is_limit:
                limit_credit = self.env['limit.credit'].sudo().search([
                    ('partner_id', '=', order.partner_id.id),
                ], limit=1)
                if limit_credit:
                    limit_credit.sudo().write({
                        'amount_limit_consumed': limit_credit.amount_limit_consumed - order.amount_total
                    })
                    self.env['limit.credit.operation'].create({
                        'limit_id': limit_credit.id,
                        'name': "Annulation Gros & 1/2 Gros - %s - %s" % (order.name, order.company_id.lib_company),
                        'amount_operation': -order.amount_total,
                        'operation_date': fields.Datetime.now(),
                    })
                    order.is_limit = False
                    self.env.invalidate_all()
                    _logger.info('Crédit utilisé mis à jour: %s', limit_credit.amount_limit_consumed)
        return True


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