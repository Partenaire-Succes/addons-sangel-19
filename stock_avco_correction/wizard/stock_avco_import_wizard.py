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

# Seuil de variation acceptée entre prix réception et prix Excel
VARIATION_THRESHOLD = 0.05  # 5%


def _compute_price(move_price, excel_price):
    """
    Retourne (prix_final, source, variation_pct)

    Règle :
      - reception = 0               → prix Excel
      - variation <= 5%             → garder prix réception
      - variation > 5%              → prendre prix Excel
    """
    if move_price <= 0:
        return excel_price, 'excel_zero', 0.0

    if excel_price <= 0:
        # Pas de prix Excel → garder le prix réception tel quel
        return move_price, 'reception_no_excel', 0.0

    variation = abs(move_price - excel_price) / excel_price

    if variation <= VARIATION_THRESHOLD:
        return move_price, 'reception_ok', variation
    else:
        return excel_price, 'excel_override', variation


class StockAvcoImportWizard(models.TransientModel):
    _name = 'stock.avco.import.wizard'
    _description = "Assistant de correction AVCO par import Excel"

    state = fields.Selection([
        ('import',  'Import fichier'),
        ('preview', 'Vérification'),
        ('done',    'Terminé'),
    ], default='import', string="Etape")

    company_id = fields.Many2one(
        'res.company', string="Societe", required=True,
        default=lambda self: self.env.company,
    )

    excel_file     = fields.Binary(string="Fichier Excel", attachment=False)
    excel_filename = fields.Char(string="Nom du fichier")

    variation_threshold = fields.Float(
        string="Seuil de variation acceptee (%)",
        default=5.0,
        help="Si la variation entre le prix reception et le prix Excel est "
             "inferieure ou egale a ce seuil, le prix reception est conserve. "
             "Sinon le prix Excel est utilise."
    )

    line_ids = fields.One2many(
        'stock.avco.import.wizard.line', 'wizard_id', string="Lignes"
    )

    summary_html         = fields.Html(string="Resume",                    readonly=True)
    nb_moves_corrected   = fields.Integer(string="Mouvements corriges",    readonly=True)
    nb_po_updated        = fields.Integer(string="Commandes mises a jour", readonly=True)
    nb_invoice_updated   = fields.Integer(string="Factures mises a jour",  readonly=True)
    nb_products_updated  = fields.Integer(string="Produits mis a jour",    readonly=True)
    total_value_injected = fields.Float(string="Valeur totale (FCFA)",     readonly=True)
    nb_not_found         = fields.Integer(string="Codes non trouves",      readonly=True)

    # ------------------------------------------------------------------
    # ÉTAPE 1 — Analyser
    # ------------------------------------------------------------------
    def action_load_file(self):
        self.ensure_one()
        if not self.excel_file:
            raise UserError(_("Veuillez selectionner un fichier Excel."))

        company   = self.company_id
        threshold = (self.variation_threshold or 5.0) / 100.0

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
                    'nb_moves_total':          0,
                    'nb_moves_reception_ok':   0,
                    'nb_moves_excel_override': 0,
                    'nb_moves_excel_zero':     0,
                    'nb_moves_no_change':      0,
                    'total_qty':    0.0,
                    'total_value':  0.0,
                    'state':        'not_found',
                })
                continue

            moves = self.env['stock.move'].search([
                ('product_id', '=', product.id),
                ('is_in', '=', True),
                ('state', '=', 'done'),
                ('company_id', '=', company.id),
            ])

            if not moves:
                lines_vals.append({
                    'wizard_id':    self.id,
                    'code_article': code_padded,
                    'product_id':   product.id,
                    'pmp_excel':    pmp_excel,
                    'nb_moves_total':          0,
                    'nb_moves_reception_ok':   0,
                    'nb_moves_excel_override': 0,
                    'nb_moves_excel_zero':     0,
                    'nb_moves_no_change':      0,
                    'total_qty':    0.0,
                    'total_value':  0.0,
                    'state':        'no_move',
                })
                continue

            # --- Analyse move par move ---
            nb_reception_ok   = 0  # variation <= seuil → prix réception conservé
            nb_excel_override = 0  # variation > seuil  → prix Excel appliqué
            nb_excel_zero     = 0  # réception à 0      → prix Excel appliqué
            nb_no_change      = 0  # réception ok ET value cohérente → rien à faire

            total_qty   = 0.0
            total_value = 0.0
            needs_fix   = False

            for move in moves:
                total_qty += move.quantity

                correct_price, source, variation = self._get_correct_price(
                    move.price_unit, pmp_excel, threshold
                )

                total_value += move.quantity * correct_price
                correct_value = move.quantity * correct_price

                if source == 'reception_ok':
                    if abs(move.value - correct_value) > 0.01:
                        nb_reception_ok += 1
                        needs_fix = True
                    else:
                        nb_no_change += 1
                elif source == 'excel_zero':
                    nb_excel_zero += 1
                    needs_fix = True
                elif source == 'excel_override':
                    nb_excel_override += 1
                    needs_fix = True
                else:
                    # reception_no_excel
                    if abs(move.value - correct_value) > 0.01:
                        nb_reception_ok += 1
                        needs_fix = True
                    else:
                        nb_no_change += 1

            lines_vals.append({
                'wizard_id':               self.id,
                'code_article':            code_padded,
                'product_id':              product.id,
                'pmp_excel':               pmp_excel,
                'nb_moves_total':          len(moves),
                'nb_moves_reception_ok':   nb_reception_ok,
                'nb_moves_excel_override': nb_excel_override,
                'nb_moves_excel_zero':     nb_excel_zero,
                'nb_moves_no_change':      nb_no_change,
                'total_qty':               total_qty,
                'total_value':             total_value,
                'state':                   'ready' if needs_fix else 'ok',
            })

        self.env['stock.avco.import.wizard.line'].create(lines_vals)

        nb_ready    = sum(1 for v in lines_vals if v['state'] == 'ready')
        nb_ok       = sum(1 for v in lines_vals if v['state'] == 'ok')
        nb_override = sum(v.get('nb_moves_excel_override', 0) for v in lines_vals)
        nb_zero     = sum(v.get('nb_moves_excel_zero', 0) for v in lines_vals)
        nb_rec_ok   = sum(v.get('nb_moves_reception_ok', 0) for v in lines_vals)

        self.summary_html = self._build_load_summary_html(
            len(rows), nb_ready, nb_ok, nb_rec_ok,
            nb_override, nb_zero, len(not_found),
            not_found, self.variation_threshold, company.name
        )
        self.state = 'preview'
        return self._reload()

    # ------------------------------------------------------------------
    # ÉTAPE 2 — Appliquer
    # ------------------------------------------------------------------
    def action_apply(self):
        self.ensure_one()

        company   = self.company_id
        threshold = (self.variation_threshold or 5.0) / 100.0

        lines_to_apply = self.line_ids.filtered(
            lambda l: l.state == 'ready' and l.product_id
        )
        if not lines_to_apply:
            raise UserError(_("Aucune ligne a corriger."))

        nb_moves_fixed = 0
        nb_po_fixed    = 0
        nb_inv_fixed   = 0
        nb_products    = 0
        total_value    = 0.0

        for line in lines_to_apply:
            moves = self.env['stock.move'].search([
                ('product_id', '=', line.product_id.id),
                ('is_in', '=', True),
                ('state', '=', 'done'),
                ('company_id', '=', company.id),
            ])
            if not moves:
                continue

            po_lines_fixed = set()
            invoices_fixed = set()
            product_touched = False

            for move in moves:
                correct_price, source, variation = self._get_correct_price(
                    move.price_unit, line.pmp_excel, threshold
                )

                if correct_price <= 0:
                    continue

                correct_value = move.quantity * correct_price

                # Mise à jour du move uniquement si nécessaire
                update_vals = {}
                if abs(move.price_unit - correct_price) > 0.01:
                    update_vals['price_unit'] = correct_price
                if abs(move.value - correct_value) > 0.01:
                    update_vals['value'] = correct_value

                if update_vals:
                    move.write(update_vals)
                    nb_moves_fixed  += 1
                    product_touched  = True

                total_value += correct_value

                pol = move.purchase_line_id

                # Correction PO — même société
                if pol and pol.company_id == company and \
                        pol.id not in po_lines_fixed and \
                        abs(pol.price_unit - correct_price) > 0.01:
                    pol.write({'price_unit': correct_price})
                    po_lines_fixed.add(pol.id)
                    nb_po_fixed    += 1
                    product_touched = True

                # Correction factures — même société
                if pol and pol.company_id == company:
                    for invoice in pol.order_id.invoice_ids.filtered(
                        lambda inv: inv.move_type == 'in_invoice'
                                    and inv.state != 'cancel'
                                    and inv.company_id == company
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
            company.name, nb_products, nb_moves_fixed, nb_po_fixed, nb_inv_fixed, total_value
        )
        return self._reload()

    def action_reset(self):
        self.line_ids.unlink()
        self.write({
            'state': 'import', 'excel_file': False, 'excel_filename': False,
            'summary_html': False, 'nb_moves_corrected': 0, 'nb_po_updated': 0,
            'nb_invoice_updated': 0, 'nb_products_updated': 0,
            'total_value_injected': 0.0, 'nb_not_found': 0,
        })
        return self._reload()

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    def _get_correct_price(self, move_price, excel_price, threshold):
        """
        Retourne (prix_final, source, variation)

        Sources :
          reception_ok       → variation <= seuil, prix réception conservé
          excel_override     → variation > seuil, prix Excel appliqué
          excel_zero         → réception à 0, prix Excel appliqué
          reception_no_excel → réception > 0 mais pas de prix Excel
        """
        if move_price <= 0:
            return excel_price, 'excel_zero', 0.0

        if excel_price <= 0:
            return move_price, 'reception_no_excel', 0.0

        variation = abs(move_price - excel_price) / excel_price

        if variation <= threshold:
            return move_price, 'reception_ok', variation
        else:
            return excel_price, 'excel_override', variation

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
                    elif any(k in h for k in ('pmp', 'prix', 'cout', 'price')):
                        headers['pmp'] = cell.column - 1

            if 'code' not in headers or 'pmp' not in headers:
                found = [str(ws.cell(1, i+1).value) for i in range(ws.max_column)
                         if ws.cell(1, i+1).value]
                raise UserError(_(
                    "Colonnes 'code article' et 'pmp' non trouvees.\nDetectees : %s"
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
                                if any(k in h for k in ('pmp', 'prix', 'cout'))), None)
                    if ci is None or pi is None:
                        raise UserError(_("Colonnes non trouvees."))
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
    def _build_load_summary_html(self, total, nb_ready, nb_ok, nb_rec_ok,
                                  nb_override, nb_zero, nb_not_found,
                                  not_found_codes, threshold, company_name):
        nf_list = ''
        if not_found_codes:
            items  = ''.join(f'<li>{c}</li>' for c in not_found_codes[:20])
            more   = (f'<li>... et {len(not_found_codes)-20} autres</li>'
                      if len(not_found_codes) > 20 else '')
            nf_list = f'<ul style="color:#dc3545">{items}{more}</ul>'

        return f"""
        <div style="font-family:Arial,sans-serif;padding:10px;">
          <div style="background:#e8f4fd;border:1px solid #bee5eb;border-radius:6px;
                      padding:8px 12px;margin-bottom:10px;font-size:13px;">
            <b>Societe :</b> {company_name} &#160;|&#160;
            <b>Seuil de variation :</b> {threshold}%
          </div>
          <div style="background:#fff8e1;border:1px solid #ffc107;border-radius:6px;
                      padding:10px;margin-bottom:10px;font-size:12px;">
            <b>Regle appliquee :</b><br/>
            &#160;&#160;Reception = 0 &#8594; Prix Excel utilise<br/>
            &#160;&#160;Variation entre reception et Excel &lt;= {threshold}% &#8594; Prix reception conserve<br/>
            &#160;&#160;Variation entre reception et Excel &gt; {threshold}% &#8594; Prix Excel utilise
          </div>
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
                &#160;&#160;Moves : variation &lt;= {threshold}% &#8594; prix reception conserve
              </td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;color:#28a745;">{nb_rec_ok}</td>
            </tr>
            <tr>
              <td style="padding:8px;border:1px solid #dee2e6;">
                &#160;&#160;Moves : variation &gt; {threshold}% &#8594; prix Excel applique
              </td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;color:#e67e22;">{nb_override}</td>
            </tr>
            <tr style="background:#f8f9fa;">
              <td style="padding:8px;border:1px solid #dee2e6;">
                &#160;&#160;Moves : reception = 0 &#8594; prix Excel applique
              </td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;color:#17a2b8;">{nb_zero}</td>
            </tr>
            <tr>
              <td style="padding:8px;border:1px solid #dee2e6;">Produits deja coherents (rien a faire)</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;color:#6c757d;">{nb_ok}</td>
            </tr>
            <tr style="background:#f8f9fa;">
              <td style="padding:8px;border:1px solid #dee2e6;">Codes non trouves dans Odoo</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;color:#dc3545;">{nb_not_found}</td>
            </tr>
          </table>
          {f'<h4 style="color:#dc3545;margin-top:12px;">Codes non trouves :</h4>{nf_list}' if nf_list else ''}
        </div>
        """

    def _build_apply_summary_html(self, nb_products, nb_moves, nb_po, nb_invoices,
                                   total_value, company_name):
        return f"""
        <div style="font-family:Arial,sans-serif;padding:10px;">
          <div style="background:#e8f4fd;border:1px solid #bee5eb;border-radius:6px;
                      padding:8px 12px;margin-bottom:10px;">
            <b>Societe :</b> {company_name}
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

    nb_moves_total          = fields.Integer(string="Total moves",           readonly=True)
    nb_moves_reception_ok   = fields.Integer(string="Var. <= seuil",         readonly=True)
    nb_moves_excel_override = fields.Integer(string="Var. > seuil (Excel)",  readonly=True)
    nb_moves_excel_zero     = fields.Integer(string="Reception = 0 (Excel)", readonly=True)
    nb_moves_no_change      = fields.Integer(string="Sans changement",       readonly=True)

    total_qty   = fields.Float(string="Qte totale",    digits=(16, 3), readonly=True)
    total_value = fields.Float(string="Valeur (FCFA)", digits=(16, 2), readonly=True)

    state = fields.Selection([
        ('ready',     'A corriger'),
        ('ok',        'Deja coherent'),
        ('not_found', 'Code non trouve'),
        ('no_move',   'Aucune reception'),
        ('done',      'Corrige'),
    ], string="Statut", readonly=True)
