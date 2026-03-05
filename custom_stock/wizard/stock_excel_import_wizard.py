from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
from openpyxl import load_workbook
import logging

_logger = logging.getLogger(__name__)


class StockExcelImportWizard(models.TransientModel):
    _name = "stock.excel.import.wizard"
    _description = "Stock Excel Import Wizard"

    file = fields.Binary(string="Excel File")
    file_name = fields.Char()

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company
    )

    location_id = fields.Many2one(
        "stock.location",
        required=True,
        domain="[('usage','=','internal')]"
    )

    line_ids = fields.One2many(
        "stock.excel.import.line",
        "wizard_id",
        string="Lines"
    )

    state = fields.Selection([
        ("draft", "Draft"),
        ("loaded", "Loaded"),
        ("done", "Done"),
    ], default="draft")

    # -------------------------
    # LOAD FILE
    # -------------------------
    def action_load_file(self):
        self.ensure_one()

        if not self.file:
            raise UserError(_("Please upload a file."))

        self.line_ids.unlink()

        decoded_file = base64.b64decode(self.file)
        file_data = io.BytesIO(decoded_file)

        workbook = load_workbook(file_data)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))

        if not rows:
            raise UserError(_("The Excel file is empty."))

        headers = [str(h).strip() for h in rows[0]]

        required_columns = ["product_code", "product_state", "quantity", "cost"]
        for col in required_columns:
            if col not in headers:
                raise UserError(_("Missing column: %s") % col)

        product_index = headers.index("product_code")
        status_index = headers.index("product_state")
        qty_index = headers.index("quantity")
        cost_index = headers.index("cost")

        env = self.env(context=dict(
            self.env.context,
            allowed_company_ids=[self.company_id.id]
        ))

        lines_vals = []

        for row in rows[1:]:

            if not row or not row[product_index]:
                continue

            product_code = str(row[product_index]).strip()
            product_state = str(row[status_index]).strip() if row[status_index] else False
            quantity = float(row[qty_index] or 0.0)
            cost = float(row[cost_index] or 0.0)

            product = env["product.product"].search(
                [("default_code", "=", product_code)],
                limit=1
            )

            lines_vals.append((0, 0, {
                "product_code": product_code,
                "product_id": product.id if product else False,
                "p_state": product_state,
                "quantity": quantity,
                "cost": cost,
                "found": bool(product),
            }))

        self.write({
            "line_ids": lines_vals,
            "state": "loaded",
        })

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    # -------------------------
    # CONFIRM INVENTORY UPDATE
    # -------------------------
    def action_confirm(self):
        self.ensure_one()

        env = self.env(context=dict(
            self.env.context,
            allowed_company_ids=[self.company_id.id]
        ))
        quants_to_apply = env["stock.quant"]
        count_lines = len(self.line_ids.filtered(lambda l: l.found))

        for line in self.line_ids.filtered(lambda l: l.found):

            product = line.product_id.with_company(self.company_id)

            status = self.env["product.status"].search([
                ("code", "=", line.p_state),
                ("active", "=", True)
            ], limit=1)

            if status:
                # ✅ Écrire sur le template avec le bon contexte société
                tmpl = product.product_tmpl_id.with_context(
                    allowed_company_ids=[self.company_id.id]
                ).with_company(self.company_id)
                tmpl.current_company_status_id = status.id

            if product:
                product.standard_price = line.cost

            quant = env["stock.quant"].search([
                ("product_id", "=", product.id),
                ("location_id", "=", self.location_id.id),
            ], limit=1)

            if quant:
                quant.inventory_quantity = line.quantity
            else:
                quant = env["stock.quant"].create({
                    "product_id": product.id,
                    "location_id": self.location_id.id,
                    "inventory_quantity": line.quantity,
                })

            quants_to_apply |= quant

        if quants_to_apply:
            quants_to_apply._apply_inventory()

        self.state = "done"

        # return {"type": "ir.actions.act_window_close"}
        return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Mise à jour du stock ligne total : %s' % count_lines,
                    'message': "Import terminé avec succès.",
                    'type': 'success',
                }
            }


class StockExcelImportLine(models.TransientModel):
    _name = "stock.excel.import.line"
    _description = "Stock Excel Import Line"

    wizard_id = fields.Many2one("stock.excel.import.wizard")

    product_id = fields.Many2one("product.product", readonly=True)
    product_name = fields.Char(related="product_id.name", string="Article", readonly=True)
    product_code = fields.Char("Code article")
    quantity = fields.Float("Quantité")
    cost = fields.Float("Coût")
    p_state = fields.Char("Statut Article", readonly=True)

    found = fields.Boolean("Produit trouvé")