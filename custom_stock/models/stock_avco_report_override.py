# -*- coding: utf-8 -*-
"""
Surcharge du rapport AVCO Justifier (stock.avco.report) natif Odoo.

Correction : la methode _compute_cumulative_fields du natif trie les
enregistrements avec records.sorted('date, id') — une chaine de caracteres
au lieu de deux cles distinctes. Le tri silencieux echoue et le rapport
affiche les couts cumules dans le mauvais ordre chronologique, rendant
l'audit AVCO impossible.

On surcharge uniquement cette methode, sans toucher au natif.
"""
from odoo import api, models


class StockAverageCostReportOverride(models.AbstractModel):
    _inherit = 'stock.avco.report'

    def _compute_cumulative_fields(self):
        for records in self.grouped(lambda m: (m.product_id, m.company_id)).values():
            # Correction : tri par deux cles separees (date ASC, id ASC)
            records = records.sorted(lambda r: (r.date, r.id))
            added_value = 0.0
            total_value = 0.0
            total_quantity = 0.0
            avco = 0.0
            for record in records:
                if record.res_model_name == 'stock.move':
                    if record.quantity > 0:
                        added_value = record.value
                    else:
                        added_value = avco * record.quantity
                    total_value += added_value
                    total_quantity += record.quantity
                elif record.res_model_name == 'product.value':
                    added_value = (record.value * total_quantity) - total_value
                    total_value = record.value * total_quantity

                avco = total_value / total_quantity if total_quantity else 0.0
                record.added_value = added_value
                record.total_value = total_value
                record.total_quantity = total_quantity
                record.avco_value = avco
