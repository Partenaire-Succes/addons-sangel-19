from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _prepare_tax_base_line_values(self):
        result = super()._prepare_tax_base_line_values()
        # Quand appelé depuis _prepare_invoice_lines (contexte invoicing=True),
        # pré-calcule et arrondit les taxes globalement sur toutes les lignes.
        # Sans ça, l'arrondi indépendant par ligne sur XOF (0 décimale) avec
        # taux mixtes (9% + 18%) produit un écart de ±1 CFA → écriture non équilibrée.
        if result and self.env.context.get('invoicing'):
            AccountTax = self.env['account.tax']
            company = self[:1].company_id or self.env.company
            AccountTax._add_tax_details_in_base_lines(result, company)
            AccountTax._round_base_lines_tax_details(result, company)
            AccountTax._fix_base_lines_tax_details_on_manual_tax_amounts(result, company)
        return result

    def write(self, vals):
        """
        Override to allow payment method modification on printed orders.
        Odoo core blocks payment changes when nb_print > 0.
        We temporarily reset nb_print to 0 to bypass this restriction,
        then restore the original value after the write.
        """
        printed_orders_nb_print = {}

        if vals.get('payment_ids'):
            printed_orders = self.filtered(lambda o: o.nb_print > 0)
            if printed_orders:
                # Store original nb_print values before bypassing
                printed_orders_nb_print = {o.id: o.nb_print for o in printed_orders}
                # Use direct SQL to avoid recursion (bypasses ORM write hooks)
                self.env.cr.execute(
                    "UPDATE pos_order SET nb_print = 0 WHERE id = ANY(%s)",
                    [list(printed_orders_nb_print.keys())]
                )
                printed_orders.invalidate_recordset(['nb_print'])

        result = super().write(vals)

        # Restore original nb_print values
        if printed_orders_nb_print:
            for order_id, nb_print in printed_orders_nb_print.items():
                self.env.cr.execute(
                    "UPDATE pos_order SET nb_print = %s WHERE id = %s",
                    [nb_print, order_id]
                )
            self.browse(list(printed_orders_nb_print.keys())).invalidate_recordset(['nb_print'])

        return result
