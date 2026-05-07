import base64
import io
import logging

import openpyxl
try:
    import xlrd
    HAS_XLRD = True
except ImportError:
    HAS_XLRD = False

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockAvcoImportWizard(models.TransientModel):
    _name = 'stock.avco.import.wizard'
    _description = "Assistant de correction AVCO par import Excel"

    state = fields.Selection([
        ('import',  'Import fichier'),
        ('preview', 'Vérification'),
        ('done',    'Terminé'),
    ], default='import', string="Étape")

    # Société active au moment de l'ouverture du wizard
    company_id = fields.Many2one(
        'res.company',
        string="Société",
        required=True,
        default=lambda self: self.env.company,
    )

    excel_file     = fields.Binary(string="Fichier Excel", attachment=False)
    excel_filename = fields.Char(string="Nom du fichier")


    line_ids = fields.One2many(
        'stock.avco.import.wizard.line', 'wizard_id',
        string="Lignes"
    )

    summary_html         = fields.Html(string="Résumé",                    readonly=True)
    nb_moves_corrected   = fields.Integer(string="Mouvements corrigés",    readonly=True)
    nb_po_updated        = fields.Integer(string="Commandes mises à jour", readonly=True)
    nb_invoice_updated   = fields.Integer(string="Factures mises à jour",  readonly=True)
    nb_products_updated  = fields.Integer(string="Produits mis à jour",    readonly=True)
    total_value_injected = fields.Float(string="Valeur totale (FCFA)",     readonly=True)
    nb_not_found         = fields.Integer(string="Codes non trouvés",      readonly=True)

    # ------------------------------------------------------------------
    # ÉTAPE 1 — Analyser le fichier
    # ------------------------------------------------------------------
    def action_load_file(self):
        self.ensure_one()
        if not self.excel_file:
            raise UserError(_("Veuillez sélectionner un fichier Excel."))

        company = self.company_id

        rows = self._parse_excel(self.excel_file, self.excel_filename)
        if not rows:
            raise UserError(_(
                "Fichier vide ou format incorrect.\n"
                "Colonnes attendues : 'code article' et 'pmp'"
            ))

        self.line_ids.unlink()
        lines_vals = []
        not_found  = []

        for code_raw, pmp_excel in rows:
            if not code_raw:
                continue

            code_padded = str(code_raw).strip().zfill(4)
            pmp_excel   = float(pmp_excel) if pmp_excel else 0.0

            # Recherche produit — les produits sont partagés entre sociétés
            # mais on vérifie qu'ils sont actifs
            product = self.env['product.product'].search([
                ('default_code', '=', code_padded),
                ('active', '=', True),
            ], limit=1)

            if not product:
                not_found.append(code_padded)
                lines_vals.append({
                    'wizard_id':    self.id,
                    'code_article': code_padded,
                    'product_id':   False,
                    'pmp_excel':    pmp_excel,
                    'nb_moves_total':        0,
                    'nb_moves_reception_ok': 0,
                    'nb_moves_po_mismatch':  0,
                    'nb_moves_zero':         0,
                    'total_qty':    0.0,
                    'total_value':  0.0,
                    'state':        'not_found',
                })
                continue

            # Mouvements UNIQUEMENT pour la société courante
            moves = self.env['stock.move'].search([
                ('product_id', '=', product.id),
                ('is_in', '=', True),
                ('state', '=', 'done'),
                ('company_id', '=', company.id),   # ← FILTRE SOCIÉTÉ
            ])

            if not moves:
                lines_vals.append({
                    'wizard_id':    self.id,
                    'code_article': code_padded,
                    'product_id':   product.id,
                    'pmp_excel':    pmp_excel,
                    'nb_moves_total':        0,
                    'nb_moves_reception_ok': 0,
                    'nb_moves_po_mismatch':  0,
                    'nb_moves_zero':         0,
                    'total_qty':    0.0,
                    'total_value':  0.0,
                    'state':        'no_move',
                })
                continue

            # Analyse move par move
            nb_reception_ok = 0
            nb_po_mismatch  = 0
            nb_zero         = 0
            total_qty       = 0.0
            total_value     = 0.0

            for move in moves:
                total_qty += move.quantity
                pol = move.purchase_line_id

                if move.price_unit > 0:
                    correct_price = move.price_unit
                    # PO doit être de la même société
                    if pol and pol.company_id == company and \
                            abs(pol.price_unit - move.price_unit) > 0.01:
                        nb_po_mismatch += 1
                    else:
                        nb_reception_ok += 1
                else:
                    nb_zero       += 1
                    correct_price  = pmp_excel

                total_value += move.quantity * correct_price

            nb_to_fix = nb_po_mismatch + nb_zero
            state = 'ready' if nb_to_fix > 0 else 'ok'

            lines_vals.append({
                'wizard_id':             self.id,
                'code_article':          code_padded,
                'product_id':            product.id,
                'pmp_excel':             pmp_excel,
                'nb_moves_total':        len(moves),
                'nb_moves_reception_ok': nb_reception_ok,
                'nb_moves_po_mismatch':  nb_po_mismatch,
                'nb_moves_zero':         nb_zero,
                'total_qty':             total_qty,
                'total_value':           total_value,
                'state':                 state,
            })

        self.env['stock.avco.import.wizard.line'].create(lines_vals)

        nb_ready      = sum(1 for v in lines_vals if v['state'] == 'ready')
        nb_ok         = sum(1 for v in lines_vals if v['state'] == 'ok')
        nb_mismatch   = sum(v.get('nb_moves_po_mismatch', 0) for v in lines_vals)
        nb_zero_total = sum(v.get('nb_moves_zero', 0) for v in lines_vals)

        self.summary_html = self._build_load_summary_html(
            len(rows), nb_ready, nb_ok, nb_mismatch,
            nb_zero_total, len(not_found), not_found, company.name
        )
        self.state = 'preview'
        return self._reload()

    # ------------------------------------------------------------------
    # ÉTAPE 2 — Appliquer les corrections
    # ------------------------------------------------------------------
    def action_apply(self):
        self.ensure_one()

        company = self.company_id

        lines_to_apply = self.line_ids.filtered(
            lambda l: l.state == 'ready' and l.product_id
        )
        if not lines_to_apply:
            raise UserError(_("Aucune ligne à corriger."))

        nb_moves_fixed  = 0
        nb_po_fixed     = 0
        nb_inv_fixed    = 0
        nb_products     = 0
        total_value     = 0.0

        for line in lines_to_apply:

            # Moves filtrés par société
            moves = self.env['stock.move'].search([
                ('product_id', '=', line.product_id.id),
                ('is_in', '=', True),
                ('state', '=', 'done'),
                ('company_id', '=', company.id),   # ← FILTRE SOCIÉTÉ
            ])
            if not moves:
                continue

            po_lines_fixed  = set()
            invoices_fixed  = set()
            product_touched = False

            for move in moves:
                pol = move.purchase_line_id

                # --------------------------------------------------
                # LOGIQUE FINALE :
                # 1. reception > 0 → prix réception = vérité
                # 2. reception = 0 → prix Excel
                # --------------------------------------------------
                if move.price_unit > 0:
                    correct_price = move.price_unit
                    correct_value = move.quantity * correct_price

                    # Recalculer value si incohérente
                    if abs(move.value - correct_value) > 0.01:
                        move.write({'value': correct_value})
                        nb_moves_fixed  += 1
                        product_touched  = True

                    # Corriger le PO (même société uniquement)
                    if pol and pol.company_id == company and \
                            pol.id not in po_lines_fixed and \
                            abs(pol.price_unit - correct_price) > 0.01:
                        pol.write({'price_unit': correct_price})
                        po_lines_fixed.add(pol.id)
                        nb_po_fixed    += 1
                        product_touched = True

                else:
                    # Réception à 0 → prix Excel
                    correct_price = line.pmp_excel
                    if correct_price <= 0:
                        continue

                    correct_value = move.quantity * correct_price
                    move.write({
                        'price_unit': correct_price,
                        'value':      correct_value,
                    })
                    nb_moves_fixed  += 1
                    product_touched  = True

                    # Corriger le PO (même société uniquement)
                    if pol and pol.company_id == company and \
                            pol.id not in po_lines_fixed and \
                            abs(pol.price_unit - correct_price) > 0.01:
                        pol.write({'price_unit': correct_price})
                        po_lines_fixed.add(pol.id)
                        nb_po_fixed += 1

                total_value += correct_value

                # Corriger les factures fournisseur (même société)
                if pol and pol.company_id == company:
                    po = pol.order_id
                    for invoice in po.invoice_ids.filtered(
                        lambda inv: inv.move_type == 'in_invoice'
                                    and inv.state != 'cancel'
                                    and inv.company_id == company   # ← FILTRE SOCIÉTÉ
                                    and inv.id not in invoices_fixed
                    ):
                        inv_lines = invoice.invoice_line_ids.filtered(
                            lambda il: il.product_id == move.product_id
                                       and abs(il.price_unit - correct_price) > 0.01
                        )
                        if inv_lines:
                            inv_lines.write({'price_unit': correct_price})
                            invoices_fixed.add(invoice.id)
                            nb_inv_fixed += 1


            if product_touched:
                nb_products += 1
            line.write({'state': 'done'})

        self.write({
            'state':                'done',
            'nb_moves_corrected':   nb_moves_fixed,
            'nb_po_updated':        nb_po_fixed,
            'nb_invoice_updated':   nb_inv_fixed,
            'nb_products_updated':  nb_products,
            'total_value_injected': total_value,
            'nb_not_found': len(self.line_ids.filtered(lambda l: l.state == 'not_found')),
        })
        self.summary_html = self._build_apply_summary_html(
            nb_products, nb_moves_fixed, nb_po_fixed,
            nb_inv_fixed, total_value, company.name
        )

        _logger.info(
            "Correction AVCO [%s] : %d produits | %d moves | %d PO | %d factures | %.2f FCFA",
            company.name, nb_products, nb_moves_fixed,
            nb_po_fixed, nb_inv_fixed, total_value
        )
        return self._reload()

    def action_reset(self):
        self.line_ids.unlink()
        self.write({
            'state': 'import', 'excel_file': False, 'excel_filename': False,
            'summary_html': False, 'nb_moves_corrected': 0,
            'nb_po_updated': 0, 'nb_invoice_updated': 0,
            'nb_products_updated': 0, 'total_value_injected': 0.0, 'nb_not_found': 0,
        })
        return self._reload()

    # ------------------------------------------------------------------
    # PARSING EXCEL
    # ------------------------------------------------------------------
    def _parse_excel(self, file_b64, filename):
        file_bytes = base64.b64decode(file_b64)
        rows = []
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            ws = wb.active
            headers = {}
            for col in ws.iter_cols(1, ws.max_column, 1, 1):
                cell = col[0]
                if cell.value:
                    h = str(cell.value).strip().lower()
                    if 'code' in h:
                        headers['code'] = cell.column - 1
                    elif any(k in h for k in ('pmp', 'prix', 'cout', 'coût', 'price')):
                        headers['pmp'] = cell.column - 1

            if 'code' not in headers or 'pmp' not in headers:
                found = [str(ws.cell(1, i+1).value) for i in range(ws.max_column)
                         if ws.cell(1, i+1).value]
                raise UserError(_(
                    "Colonnes 'code article' et 'pmp' non trouvées.\n"
                    "Colonnes detectees : %s"
                ) % ', '.join(found))

            for row in ws.iter_rows(min_row=2, values_only=True):
                code = row[headers['code']]
                pmp  = row[headers['pmp']]
                if code is not None:
                    try:
                        rows.append((str(code).strip(), float(pmp) if pmp else 0.0))
                    except (ValueError, TypeError):
                        continue

        except UserError:
            raise
        except Exception as e:
            if HAS_XLRD:
                try:
                    wb  = xlrd.open_workbook(file_contents=file_bytes)
                    ws  = wb.sheet_by_index(0)
                    hdr = [str(ws.cell_value(0, c)).strip().lower() for c in range(ws.ncols)]
                    ci  = next((i for i, h in enumerate(hdr) if 'code' in h), None)
                    pi  = next((i for i, h in enumerate(hdr)
                                if any(k in h for k in ('pmp', 'prix', 'cout', 'coût'))), None)
                    if ci is None or pi is None:
                        raise UserError(_("Colonnes non trouvees dans le fichier .xls"))
                    for r in range(1, ws.nrows):
                        code = str(ws.cell_value(r, ci)).strip()
                        pmp  = ws.cell_value(r, pi)
                        if code:
                            try:
                                rows.append((code, float(pmp) if pmp else 0.0))
                            except (ValueError, TypeError):
                                continue
                except UserError:
                    raise
                except Exception as e2:
                    raise UserError(_("Impossible de lire le fichier : %s") % str(e2))
            else:
                raise UserError(_("Impossible de lire le fichier : %s") % str(e))
        return rows

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------
    def _build_load_summary_html(self, total, nb_ready, nb_ok,
                                  nb_mismatch, nb_zero, nb_not_found,
                                  not_found_codes, company_name):
        nf_list = ''
        if not_found_codes:
            items  = ''.join(f'<li>{c}</li>' for c in not_found_codes[:20])
            more   = (f'<li>... et {len(not_found_codes)-20} autres</li>'
                      if len(not_found_codes) > 20 else '')
            nf_list = f'<ul style="color:#dc3545">{items}{more}</ul>'

        return f"""
        <div style="font-family:Arial,sans-serif;padding:10px;">
          <div style="background:#e8f4fd;border:1px solid #bee5eb;border-radius:6px;
                      padding:8px 12px;margin-bottom:12px;">
            <strong>Societe active :</strong> {company_name}
          </div>
          <h3 style="border-bottom:2px solid #dee2e6;padding-bottom:8px;">
            Resultat de l'analyse
          </h3>
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#f8f9fa;">
              <td style="padding:8px;border:1px solid #dee2e6;">Total produits dans le fichier</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;">{total}</td>
            </tr>
            <tr>
              <td style="padding:8px;border:1px solid #dee2e6;">Produits avec corrections a appliquer</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;color:#28a745;">{nb_ready}</td>
            </tr>
            <tr style="background:#f8f9fa;">
              <td style="padding:8px;border:1px solid #dee2e6;">
                Moves ou PO est different de la Reception
              </td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;color:#fd7e14;">{nb_mismatch}</td>
            </tr>
            <tr>
              <td style="padding:8px;border:1px solid #dee2e6;">
                Moves ou Reception = 0 (prix Excel utilise)
              </td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;color:#17a2b8;">{nb_zero}</td>
            </tr>
            <tr style="background:#f8f9fa;">
              <td style="padding:8px;border:1px solid #dee2e6;">Produits deja coherents (rien a faire)</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;color:#6c757d;">{nb_ok}</td>
            </tr>
            <tr>
              <td style="padding:8px;border:1px solid #dee2e6;">Code article non trouve dans Odoo</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;color:#dc3545;">{nb_not_found}</td>
            </tr>
          </table>
          {f'<h4 style="color:#dc3545;margin-top:16px;">Codes non trouves :</h4>{nf_list}' if nf_list else ''}
        </div>
        """

    def _build_apply_summary_html(self, nb_products, nb_moves, nb_po,
                                   nb_invoices, total_value, company_name):
        return f"""
        <div style="font-family:Arial,sans-serif;padding:10px;">
          <div style="background:#e8f4fd;border:1px solid #bee5eb;border-radius:6px;
                      padding:8px 12px;margin-bottom:12px;">
            <strong>Societe :</strong> {company_name}
          </div>
          <h3 style="border-bottom:2px solid #28a745;padding-bottom:8px;color:#28a745;">
            Corrections appliquees avec succes !
          </h3>
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#f8f9fa;">
              <td style="padding:8px;border:1px solid #dee2e6;">Produits traites</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;">{nb_products}</td>
            </tr>
            <tr>
              <td style="padding:8px;border:1px solid #dee2e6;">Mouvements de stock corriges</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;">{nb_moves}</td>
            </tr>
            <tr style="background:#f8f9fa;">
              <td style="padding:8px;border:1px solid #dee2e6;">Commandes d'achat mises a jour</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;">{nb_po}</td>
            </tr>
            <tr>
              <td style="padding:8px;border:1px solid #dee2e6;">Factures fournisseurs mises a jour</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;">{nb_invoices}</td>
            </tr>
            <tr style="background:#f8f9fa;">
              <td style="padding:8px;border:1px solid #dee2e6;">Valeur totale recalculee</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;">
                {total_value:,.2f} FCFA
              </td>
            </tr>
          </table>
        </div>
        """

    def _reload(self):
        return {
            'type':      'ir.actions.act_window',
            'res_model': self._name,
            'res_id':    self.id,
            'view_mode': 'form',
            'target':    'new',
        }


class StockAvcoImportWizardLine(models.TransientModel):
    _name = 'stock.avco.import.wizard.line'
    _description = "Ligne de correction AVCO"
    _order = 'state, code_article'

    wizard_id    = fields.Many2one('stock.avco.import.wizard', ondelete='cascade')
    code_article = fields.Char(string="Code Article",  readonly=True)
    product_id   = fields.Many2one('product.product',  string="Produit",   readonly=True)
    pmp_excel    = fields.Float(string="PMP Excel (FCFA)", digits=(16, 2), readonly=True)

    nb_moves_total        = fields.Integer(string="Total moves",       readonly=True)
    nb_moves_reception_ok = fields.Integer(string="PO = Reception",    readonly=True)
    nb_moves_po_mismatch  = fields.Integer(string="PO diff. Reception", readonly=True)
    nb_moves_zero         = fields.Integer(string="Reception = 0",     readonly=True)

    total_qty   = fields.Float(string="Qte totale",    digits=(16, 3), readonly=True)
    total_value = fields.Float(string="Valeur (FCFA)", digits=(16, 2), readonly=True)

    state = fields.Selection([
        ('ready',     'A corriger'),
        ('ok',        'Deja coherent'),
        ('not_found', 'Code non trouve'),
        ('no_move',   'Aucune reception'),
        ('done',      'Corrige'),
    ], string="Statut", readonly=True)
