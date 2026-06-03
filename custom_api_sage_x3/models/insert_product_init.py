import re
import time
import gc
import logging

import requests

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MAX_RETRIES  = 3
PAGE_SIZE    = 100
COMMIT_STEP  = 20
MAX_PAGES    = 1000
TIMEOUT      = 30
MAX_DURATION = 300  # 5 minutes

# Champs mis à jour sur un produit existant (le nom et default_code sont exclus intentionnellement)
_PRODUCT_UPDATE_FIELDS = (
    'barcode', 'description', 'list_price', 'taxes_id', 'supplier_taxes_id',
    'price_unit_ttc', 'prod_cond', 'weight', 'marque',
    'discount_ligne', 'airsi_taxes_id', 'price_catalog', 'price_carton',
    'price_negoce', 'price_ecom', 'price_gm', 'price_rh', 'price_st',
    'is_yop_demi_gros', 'is_yop_detail', 'is_synacass_ci', 'is_square',
    'is_bassam', 'is_koumassi', 'is_abobo', 'allowed_company_ids', 'family_categ_id',
    'categ_id', 'actif_x3', 'type', 's_family_id', 'radius_id', 's_radius_id',
    'uom_ids',
)


class ProductTemplateImport(models.Model):
    _name    = 'product.template'
    _inherit = ['product.template', 'sage.x3.mixin']

    # =========================================================================
    # POINTS D'ENTRÉE
    # =========================================================================


    def _normalize_taxes_for_field(self, field_name, is_airsi):
        """Normalise les taxes TVA ou AIRSI sur toutes les sociétés."""
        label = "AIRSI" if is_airsi else "TVA"
        _logger.info("🚀 Début normalisation taxes %s multi-sociétés", label)

        Tax     = self.env['account.tax'].sudo()
        Company = self.env['res.company'].sudo()
        products = self.env['product.template'].with_context(active_test=False).search([])

        total      = len(products)
        batch_size = 200

        for i in range(0, total, batch_size):
            batch = products[i:i + batch_size]

            for product in batch:
                try:
                    taxes = product[field_name]

                    # 🚫 Aucune taxe → skip
                    if not taxes:
                        continue

                    base_tax = taxes[0]
                    amount   = base_tax.amount

                    # Montant nul → vider les taxes
                    if not amount:
                        product.write({field_name: [(6, 0, [])]})
                        continue

                    new_tax_ids = []

                    for company in Company.search([]):
                        tax = Tax.with_company(company).search([
                            ('amount',      '=', amount),
                            ('amount_type', '=', 'percent'),
                            ('type_tax_use','=', 'sale'),
                            ('company_id',  '=', company.id),
                            ('is_airsi',    '=', is_airsi),  # ✅ filtre clé
                        ], limit=1)

                        if not tax:
                            name = f"TVA AIRSI {amount}%" if is_airsi else f"TVA {amount}%"  # ✅
                            tax = Tax.with_company(company).create({
                                'name':         name,
                                'amount':       amount,
                                'amount_type':  'percent',
                                'type_tax_use': 'sale',
                                'company_id':   company.id,
                                'is_airsi':     is_airsi,  # ✅
                            })

                        new_tax_ids.append(tax.id)

                    product.write({field_name: [(6, 0, new_tax_ids)]})

                except Exception as e:
                    _logger.error("❌ Erreur produit %s : %s", product.default_code, str(e))

            self.env.cr.commit()
            _logger.info("💾 Batch %s / %s traité", i, total)

        _logger.info("✅ Normalisation %s terminée", label)


    def normalize_taxes_tva_all_companies(self):
        self._normalize_taxes_for_field('taxes_id', is_airsi=False)


    def normalize_taxes_airsi_all_companies(self):
        self._normalize_taxes_for_field('airsi_taxes_id', is_airsi=True)

    def reset_airsi_taxes_all_products(self):
        """Supprime toutes les taxes AIRSI de tous les produits pour reprendre l'import."""
        _logger.info("🚀 Début suppression taxes AIRSI sur tous les produits")

        # ✅ Étape 1 : Trouver les taxes AIRSI
        airsi_taxes = self.env['account.tax'].with_context(active_test=False).search([
            ('name', 'ilike', 'AIRSI')
        ])

        if not airsi_taxes:
            _logger.warning("⚠️ Aucune taxe AIRSI trouvée dans le système")
            return

        _logger.info("🔎 %s taxe(s) AIRSI trouvée(s) : %s", len(airsi_taxes), airsi_taxes.mapped('name'))

        # ✅ Étape 2 : Filtrer les produits via 'in' sur les IDs — fonctionne sur les M2M
        products = self.env['product.template'].with_context(active_test=False).search([
            ('airsi_taxes_id', 'in', airsi_taxes.ids)
        ])

        total = len(products)
        _logger.info("📦 %s produits avec taxes AIRSI trouvés", total)

        for idx, product in enumerate(products):
            try:
                product.write({'airsi_taxes_id': [(5, 0, 0)]})
            except Exception as e:
                _logger.error("❌ Erreur produit %s : %s", product.default_code, str(e))

            if (idx + 1) % 200 == 0:
                self.env.cr.commit()
                _logger.info("💾 %s / %s traités", idx + 1, total)

        self.env.cr.commit()
        _logger.info("✅ Suppression terminée — %s produits mis à jour", total)
    

    def import_products_job(self):
        self.action_import_products_external_source()

    def action_delete_products_no_company(self):
        products = self.env['product.template'].with_context(
            active_test=False
        ).search([('allowed_company_ids', '=', False), ('type', '=', 'consu')])

        count = len(products)
        products.unlink()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Suppression effectuée',
                'message': f'{count} produit(s) supprimé(s).',
                'type': 'success',
                'sticky': False,
            },
        }

    def action_import_products_external_source(self):
        """
        Importe les produits depuis l'API SAGE X3.
        • Récupération et traitement page par page (pas d'accumulation mémoire)
        • Commit tous les COMMIT_STEP produits
        • Rollback par produit en cas d'erreur isolée
        • Arrêt automatique après MAX_DURATION secondes (récupération ET traitement)
        • Cache des taxes partagé sur tout l'import
        """
        try:
            token = self._authenticate_sage_x3()
            if not token:
                raise UserError("Échec de l'authentification SAGE X3")

            config = self._get_sage_x3_config()
            if isinstance(config, dict):
                base_url = config.get('base_url') or config.get(0)
            else:
                base_url = config[0]
            items_url = f"{base_url}/api/Items"
            headers   = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

            created = updated = skipped = errors = price_updated = suppliers_added = 0
            tmpl_model = self.env['product.template']
            tax_cache  = {}   # {(amount, is_airsi): [tax_ids]} — évite les appels BDD répétés
            page       = 1
            idx        = 0
            start_time = time.time()

            while page <= MAX_PAGES:
                if time.time() - start_time > MAX_DURATION:
                    _logger.warning("⏱️ Import interrompu : durée maximale atteinte (%ss)", MAX_DURATION)
                    break

                params   = {"pageNumber": page, "pageSize": PAGE_SIZE}
                response = self._safe_get_paged(items_url, headers, params)
                data     = response.json()
                page_items = data.get("items", [])
                _logger.info("📦 Page %s récupérée (%s produits)", page, len(page_items))

                for item in page_items:
                    idx += 1

                    if time.time() - start_time > MAX_DURATION:
                        _logger.warning("⏱️ Traitement interrompu : durée maximale atteinte (%ss)", MAX_DURATION)
                        break

                    try:
                        vals = tmpl_model.prepare_product_values(item, tax_cache)

                        if not vals.get("default_code"):
                            _logger.warning("⚠️ Produit ignoré sans default_code : %s", vals.get("name"))
                            skipped += 1
                            continue

                        if "SF" in str(vals.get("default_code", "")).upper():
                            _logger.info("⏭️ Produit ignoré (code SF) : %s", vals.get("default_code"))
                            skipped += 1
                            continue

                        if not any([
                            vals.get("is_yop_demi_gros"),
                            vals.get("is_yop_detail"),
                            vals.get("is_synacass_ci"),
                            vals.get("is_square"),
                            vals.get("is_koumassi"),
                            vals.get("is_bassam"),
                            vals.get("is_abobo"),
                        ]):
                            _logger.warning("⚠️ Produit ignoré aucune societe associée : %s", vals.get("name"))
                            skipped += 1
                            continue

                        existing = tmpl_model.search(
                            [("default_code", "=", vals["default_code"])], limit=1
                        )

                        if existing:
                            new_price = vals.get("list_price", 0)
                            old_price = existing.list_price

                            tmpl_model._update_existing_product(existing, vals)

                            if old_price != new_price:
                                _logger.info("💰 Prix mis à jour %s : %.2f → %.2f",
                                            existing.default_code, old_price, new_price)
                                price_updated += 1

                            tmpl_model._create_pricelist_items(existing, item)
                            tmpl_model._update_product_barcode(existing, item)
                            n = tmpl_model._update_product_suppliers(existing, item)
                            suppliers_added += n
                            updated += 1
                        else:
                            product = tmpl_model.create(vals)
                            _logger.info("✅ Créé : %s (%s)", product.name, product.default_code)
                            tmpl_model._create_pricelist_items(product, item)
                            tmpl_model._update_product_barcode(product, item)
                            n = tmpl_model._update_product_suppliers(product, item)
                            suppliers_added += n
                            created += 1

                        if idx % COMMIT_STEP == 0:
                            self.env.cr.commit()
                            gc.collect()
                            _logger.info("💾 Commit après %s produits", idx)

                    except Exception as e:
                        errors += 1
                        _logger.exception("❌ Erreur produit %s : %s", item.get("itmdeS1_0"), str(e))
                        try:
                            if not self.env.cr.closed:
                                self.env.cr.rollback()
                                self.env.invalidate_all()
                            else:
                                _logger.warning("⚠️ Curseur déjà fermé, rollback impossible")
                            tmpl_model = self.env['product.template']
                            tax_cache  = {}  # réinitialiser après rollback (IDs potentiellement invalides)
                        except Exception as rollback_err:
                            _logger.warning("⚠️ Rollback échoué : %s", str(rollback_err))

                if not data.get("hasNextPage", False):
                    break
                page += 1

            self.env.cr.commit()

            _logger.info("=" * 50)
            _logger.info("=== RÉSUMÉ IMPORTATION PRODUITS ===")
            _logger.info("✅ Créés        : %s", created)
            _logger.info("🔄 Mis à jour   : %s", updated)
            _logger.info("💰 Prix modifiés: %s", price_updated)
            _logger.info("🏭 Fournisseurs : %s", suppliers_added)
            _logger.info("⏩ Ignorés      : %s", skipped)
            _logger.info("❌ Erreurs      : %s", errors)
            _logger.info("=" * 50)

        except Exception as e:
            _logger.exception("🚨 Échec global de l'importation : %s", str(e))
            raise UserError("L'importation des produits a échoué.")

    # =========================================================================
    # HTTP — GET PAGINÉ
    # =========================================================================

    def _safe_get_paged(self, url, headers, params, timeout=TIMEOUT):
        """GET avec retry et timeout (pour pagination)."""
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
                if response.status_code in (200, 201):
                    return response
                _logger.warning("⚠️ HTTP inattendu (tentative %s) : %s", attempt, response.status_code)
                last_exc = Exception(f"HTTP {response.status_code}")
            except requests.exceptions.RequestException as e:
                _logger.warning("⚠️ Exception réseau (tentative %s) : %s", attempt, str(e))
                last_exc = e
            time.sleep(5)
        raise UserError(f"Échec de récupération après {MAX_RETRIES} tentatives : {last_exc}")

    # =========================================================================
    # OUTILS DE CONVERSION
    # =========================================================================

    def _safe_float(self, value, default=0.0):
        if not value:
            return default
        try:
            return float(str(value).replace(",", ".").replace(" ", ""))
        except (ValueError, TypeError):
            return default

    def _safe_string(self, value, default=""):
        if not value or str(value).strip() == "":
            return default
        return str(value).strip()

    def _verify_boolean(self, value):
        """Convertit la valeur SAGE X3 (0/1/2) en booléen Odoo."""
        v = self._safe_float(value)
        if v == 2:
            return True
        if v in (0, 1):
            return False
        _logger.warning("⚠️ Valeur non reconnue pour boolean : %s", value)
        return False

    # =========================================================================
    # GESTION DES TAXES
    # =========================================================================

    def _extract_tax_amount(self, tax_code):
        if not tax_code:
            return 0.0

        tax_code = str(tax_code).strip().upper()

        try:
            if tax_code == "T18":
                return 18.0
            elif tax_code == "T09":
                return 9.0
            elif tax_code == "T00":
                return 0.0
            elif tax_code == "1,500":
                return 1.5
            elif tax_code == "5,000":
                return 5.0

            return float(tax_code)

        except ValueError:
            pass

        numbers = re.findall(r"\d+\.?\d*", tax_code)
        return float(numbers[0]) if numbers else 0.0

    def _get_ht_price(self, price, tax):
        """Calcule le prix HT depuis le prix TTC et le code taxe."""
        price_ttc  = self._safe_float(price)
        tax_amount = self._extract_tax_amount(tax)
        if tax_amount > 0:
            return round(price_ttc / (1 + tax_amount / 100), 2)
        return price_ttc

    def _get_or_create_tax_group(self, amount, company):
        name = f"TVA {amount}%"
        env  = self.env['account.tax.group'].sudo().with_company(company)
        rec  = env.search([("name", "=", name), ("company_id", "=", company.id)], limit=1)
        if rec:
            return rec
        try:
            return env.create({"name": name, "company_id": company.id})
        except Exception:
            return (
                env.search([("company_id", "=", company.id)], limit=1)
                or env.create({"name": "Taxe générique", "company_id": company.id})
            )

    def _get_or_create_tax(self, name, amount, company, actif):
        """Cherche ou crée une taxe pour une société donnée."""
        # sudo() pour contourner les règles multi-sociétés lors de la création
        env_tax = self.env['account.tax'].sudo().with_company(company)
        tax = env_tax.search([
            ("amount",       "=",  amount),
            ("amount_type",  "=",  "percent"),
            ("type_tax_use", "=",  "sale"),
            ("company_id",   "=",  company.id),
            ("is_airsi",    "=", actif),
        ], limit=1)
        if tax:
            return tax

        group      = self._get_or_create_tax_group(amount, company)
        country_id = company.country_id.id if company.country_id else False
        if not country_id:
            country    = self.env['res.country'].search([('code', '=', 'CI')], limit=1)
            country_id = country.id if country else self.env['res.country'].search([], limit=1).id

        return env_tax.create({
            "name":         name,
            "amount":       amount,
            "amount_type":  "percent",
            "type_tax_use": "sale",
            "tax_group_id": group.id,
            "company_id":   company.id,
            "country_id":   country_id,
            "is_airsi": actif,
        })

    def _get_taxes_id(self, tax_code, tax_cache=None):
        """
        Retourne les taxes pour toutes les sociétés.
        - Si taxe = 0% => supprime toutes les taxes
        - Sinon => crée/récupère la taxe pour chaque société et retourne tous les IDs
        - tax_cache : dict partagé {(amount, is_airsi): [ids]} pour éviter les appels BDD répétés
        """
        amount = self._extract_tax_amount(tax_code)

        if not amount or amount == 0.0:
            return [(6, 0, [])]

        cache_key = (amount, False)
        if tax_cache is not None and cache_key in tax_cache:
            return [(6, 0, tax_cache[cache_key])]

        all_tax_ids = []
        for company in self.env['res.company'].sudo().search([]):
            tax = self._get_or_create_tax(f"TVA {amount}%", amount, company, False)
            all_tax_ids.append(tax.id)

        if tax_cache is not None:
            tax_cache[cache_key] = all_tax_ids

        return [(6, 0, all_tax_ids)]

    def _get_airsi_taxes_id(self, tax_code, tax_cache=None):
        amount = self._extract_tax_amount(tax_code)

        if not amount or amount == 0.0:
            return [(6, 0, [])]

        cache_key = (amount, True)
        if tax_cache is not None and cache_key in tax_cache:
            return [(6, 0, tax_cache[cache_key])]

        all_tax_ids = []
        for company in self.env['res.company'].sudo().search([]):
            tax = self._get_or_create_tax(f"TVA AIRSI {amount}%", amount, company, True)
            all_tax_ids.append(tax.id)

        if tax_cache is not None:
            tax_cache[cache_key] = all_tax_ids

        return [(6, 0, all_tax_ids)]
    

    # =========================================================================
    # PRÉPARATION DES VALEURS PRODUIT
    # =========================================================================

    def prepare_product_values(self, item, tax_cache=None):
        """Construit le dict de valeurs pour create/write d'un product.template."""
        barcode          = item.get("saN_CB_0", "").strip()
        invalid_barcodes = {"", "0", "00", "000", "0000", "00000"}

        if not barcode or barcode in invalid_barcodes:
            barcode = False
        else:
            if len(barcode) == 13 and barcode.startswith('27') and barcode.endswith('0000000'):
                old_barcode = barcode
                barcode     = self.fix_gs1_barcode(barcode)
                _logger.info("🔧 Code-barres GS1 corrigé : %s → %s", old_barcode, barcode)

            if barcode:
                existing = self.search([("barcode", "=", barcode)], limit=1)
                if existing:
                    _logger.warning("⚠️ Barcode déjà utilisé (%s) par %s — ignoré",
                                    barcode, existing.default_code)
                    barcode = False

        tax_code       = item.get("vacitM_0")
        family_id      = self._get_family_id(item.get("yG5FAM_0"))
        base_price_ttc = self._safe_float(item.get("basprI_0"))

        vals = {
            "name":              item.get("itmdeS1_0") or "Produit sans nom",
            "default_code":      item.get("itmreF_0") or False,
            "barcode":           barcode,
            "description":       item.get("itmdeS2_0", ""),
            "list_price":        self._get_ht_price(item.get("ypV_SAN_0"), tax_code),
            "taxes_id":          self._get_taxes_id(tax_code, tax_cache),
            "supplier_taxes_id": False,
            "price_unit_ttc":    self._safe_float(item.get("ypV_SAN_0")),
            "uom_id":            self._get_uom_id(item.get("saU_0")),
            "prod_cond":         item.get("ypcB1_0", ""),
            "weight":            self._safe_float(item.get("itmweI_0")),
            "marque":            item.get("ymarK_0", ""),
            "discount_ligne":    self._verify_boolean(item.get("yappremL_0")),
            "airsi_taxes_id":    self._get_airsi_taxes_id(item.get("yairsI_0"), tax_cache),
            "price_catalog":     base_price_ttc,
            "price_carton":      self._safe_float(item.get("ypxcA_0")),
            "price_negoce":      self._safe_float(item.get("ypxneG_0")),
            "price_ecom":        self._safe_float(item.get("yglovttC_0")),
            "price_gm":          round(base_price_ttc * 1.05, 2),
            "price_rh":          round(base_price_ttc * 1.02, 2),
            "price_st":          round(base_price_ttc * 1.01, 2),
            "is_yop_demi_gros":  self._verify_boolean(item.get("yafdM_0")),
            "is_yop_detail":     self._verify_boolean(item.get("yafdeT_0")),
            "is_synacass_ci":    self._verify_boolean(item.get("yafsyN_0")),
            "is_square":         self._verify_boolean(item.get("yafsQ_0")),
            "is_bassam":         self._verify_boolean(item.get("yafbsM_0")),
            "is_koumassi":       self._verify_boolean(item.get("yafkouM_0")),
            "is_abobo":          self._verify_boolean(item.get("yafdoK_0")),
            "allowed_company_ids": self._get_allowed_company_ids(item),
            "family_categ_id":   family_id,
            "categ_id":          family_id,
            "actif_x3":          self._safe_string(item.get("itmstA_0")),
            "type":              "consu" if item.get("yG5TYPE_0") == "TS" else "service",
            "active":            True,
            "sale_ok":           True,
            "purchase_ok":       True,
            "available_in_pos":  True,
            "is_storable":       True,
            "uom_ids":           [(5, 0, 0)],
        }

        # uom_ids = self._get_uom_ids(item.get("ypcB1_0"), item.get("saU_0"))
        # if uom_ids is not None:
        #     vals["uom_ids"] = uom_ids

        # Champs Many2one optionnels — non inclus si vide pour ne pas écraser la valeur existante
        for field, value in [
            ("code_inventory_id", self._get_code_inventory_id(item.get("yG5EMPLC_0"))),
            ("s_family_id",       self._get_sub_family_id(item.get("yG5SFAM_0"))),
            ("radius_id",         self._get_radius_id(item.get("yG5RAY_0"))),
            ("s_radius_id",       self._get_sub_radius_id(item.get("yG5SRAY_0"))),
            ("cat_gestion_id",    self._get_prod_gestion_id(item.get("tclcoD_0"))),
            ("prod_family_x3_id", self._get_prod_family_id(item.get("tsicoD_0"))),
            ("prod_type_x3_id",   self._get_prod_type_id(item.get("yG5TYPE_0"))),
            ("prod_status_x3_id", self._get_prod_status_id(item.get("yG5STAT_0"))),
        ]:
            if value:
                vals[field] = value

        return vals

    # =========================================================================
    # GESTION DES FOURNISSEURS
    # =========================================================================

    def _update_product_barcode(self, product, item):
        """Ajoute le barcode secondaire (yG5BC_0) dans product.multiple.barcodes si absent."""
        barcode = self._safe_string(item.get("yG5BC_0"))
        if not barcode or barcode in {"0", "00", "000", "0000", "00000"}:
            return False
        try:
            multi_code = self.env['product.multiple.barcodes']
            already = multi_code.search([
                '|',
                ('product_id', '=', product.product_variant_id.id),
                ('product_multi_barcode', '=', barcode)
            ], limit=1)
            if already:
                return 0

            multi_code.create({
                'product_multi_barcode': barcode,
                'product_id':            product.product_variant_id.id,
                'product_tmpl_id':       product.id,
            })
            _logger.info("🏭 Barcode secondaire %s ajouté au produit %s", barcode, product.default_code)
            return 1
        except Exception as e:
            _logger.warning("⚠️ Barcode secondaire %s ignoré (%s) : %s", barcode, product.default_code, e)
            return False

    def _update_existing_product(self, existing, vals):
        """
        Met à jour uniquement les champs autorisés (_PRODUCT_UPDATE_FIELDS) sur un produit existant.
        Le nom (name) et la référence (default_code) ne sont jamais modifiés ici.
        Le barcode n'est pas écrasé par False quand le produit possède déjà un code-barres valide.
        """
        update_vals = {f: vals[f] for f in _PRODUCT_UPDATE_FIELDS if f in vals}

        # Si le barcode calculé est False (conflit auto-détecté avec le produit lui-même),
        # on conserve le barcode existant plutôt que de l'effacer.
        if not update_vals.get('barcode') and existing.barcode:
            update_vals.pop('barcode', None)

        existing.write(update_vals)

    def _update_product_suppliers(self, product, item):
        """Crée ou met à jour la ligne fournisseur d'un produit. Retourne le nombre de lignes ajoutées."""
        supplier_code = self._safe_string(item.get("yG5FRS_0"))
        if not supplier_code:
            return 0

        try:
            SupplierInfo = self.env['product.supplierinfo']

            supplier = self.env['res.partner'].search([
                '|',
                ('ref', '=', supplier_code),
                ('name', '=', supplier_code),
                ('supplier_rank', '>', 0),
            ], limit=1)

            if not supplier:
                supplier = self.env['res.partner'].create({
                    'name':          supplier_code,
                    'ref':           supplier_code,
                    'supplier_rank': 1,
                    'is_company':    True,
                })
                _logger.info("➕ Fournisseur créé : %s", supplier_code)

            existing = SupplierInfo.search([
                ('product_tmpl_id', '=', product.id),
                ('partner_id',      '=', supplier.id),
            ], limit=1)

            if existing:
                existing.write({
                    'min_qty':         1.0,
                    'primary':         True,
                })
                
                _logger.info("🏭 Fournisseur mis à jour au produit %s : %s",
                             product.default_code, supplier.name)
                return 1

            SupplierInfo.create({
                'partner_id':      supplier.id,
                'product_tmpl_id': product.id,
                'min_qty':         1.0,
                'primary':         True,
                'currency_id':     self.env.company.currency_id.id,
            })
            _logger.info("🏭 Fournisseur ajouté au produit %s : %s",
                         product.default_code, supplier.name)
            return 1

        except Exception as e:
            _logger.error("❌ Erreur fournisseur pour %s : %s", product.default_code, str(e))
            return 0

    # =========================================================================
    # LISTES DE PRIX
    # =========================================================================

    def _create_pricelist_items(self, product, item):
        """Crée ou met à jour les lignes de liste de prix pour un produit."""
        PricelistItem = self.env['product.pricelist.item']
        tax_code      = item.get('vacitM_0')

        pricelist_mappings = [
            ('custom_stock.basic_retailing_price', 'ypV_SAN_0',   'PRIX VENTE DE BASE TTC',   1.0),
            ('custom_stock.catalog_sale_price',    'basprI_0',    'PRIX VENTE CATALOGUE',      1.0),
            ('custom_stock.carton_sale_price',     'ypxcA_0',     'PRIX VENTE CARTON TTC',     1.0),
            ('custom_stock.retail_sale_price',     'ypxneG_0',    'PRIX VENTE NEGOCE TTC',     1.0),
            ('custom_stock.e_commerce_sale_price', 'yglovttC_0',  'PRIX VENTE E-COMMERCE TTC', 1.0),
            ('custom_stock.gm_sale_price',         'basprI_0',    'TARIF GMS',                 1.05),
            ('custom_stock.rh_sale_price',         'basprI_0',    'TARIF RHF',                 1.02),
            ('custom_stock.st_sale_price',         'basprI_0',    'TARIF STATION',             1.01),
        ]

        for xml_id, api_field, display_name, multiplier in pricelist_mappings:
            price_ttc = self._safe_float(item.get(api_field))
            if not price_ttc or price_ttc <= 0:
                continue

            if api_field == "basprI_0":
                price_ht = round(price_ttc * multiplier, 2)
            else:
                price_ht = round(self._get_ht_price(price_ttc, tax_code) * multiplier, 2)

            try:
                pricelist = self.env.ref(xml_id, raise_if_not_found=False)
                if not pricelist:
                    _logger.warning("⚠️ Liste de prix introuvable : %s", xml_id)
                    continue

                existing_item = PricelistItem.search([
                    ('pricelist_id',    '=', pricelist.id),
                    ('product_tmpl_id', '=', product.id),
                ], limit=1)

                if existing_item:
                    existing_item.write({'fixed_price': price_ht})
                else:
                    PricelistItem.create({
                        'pricelist_id':       pricelist.id,
                        'product_tmpl_id':    product.id,
                        'compute_price':      'fixed',
                        'fixed_price':        price_ht,
                        'display_applied_on': '1_product',
                        'min_quantity':       1,
                    })

            except Exception as e:
                _logger.error("❌ Erreur prix %s (%s) : %s",
                              product.default_code, display_name, str(e))

    # =========================================================================
    # GESTION DES CODES-BARRES GS1
    # =========================================================================

    def fix_gs1_barcode(self, current_barcode):
        """Recalcule la clé de contrôle GS1 d'un EAN-13."""
        barcode_str = str(current_barcode).strip()
        if len(barcode_str) != 13:
            _logger.info("⚠️ Code %s : pas 13 caractères, ignoré", barcode_str)
            return barcode_str

        base_code = barcode_str[:12]
        odd_sum = even_sum = 0
        for i, digit in enumerate(base_code):
            d = int(digit)
            if (i + 1) % 2 == 0:
                even_sum += d
            else:
                odd_sum += d

        check_digit = (10 - ((even_sum * 3 + odd_sum) % 10)) % 10
        return base_code + str(check_digit)

    def update_products_barcodes(self, product, item):
        """Met à jour le code-barres GS1 si nécessaire."""
        barcode = self._safe_string(item.get("saN_CB_0"))
        if not barcode or len(barcode) != 13:
            return
        if not (barcode.startswith('27') and barcode.endswith('0000000')):
            return

        new_barcode = self.fix_gs1_barcode(barcode)
        if barcode == new_barcode:
            return

        try:
            conflict = self.search([
                ("barcode", "=", new_barcode),
                ("id", "!=", product.id),
            ], limit=1)

            if conflict:
                _logger.warning(
                    "⚠️ Barcode corrigé %s déjà utilisé par %s — conservation de %s pour %s",
                    new_barcode, conflict.default_code, barcode, product.default_code,
                )
                return

            product.write({'barcode': new_barcode})
            _logger.info("✅ Barcode corrigé %s : %s → %s",
                         product.default_code, barcode, new_barcode)
        except Exception as e:
            _logger.error("❌ Erreur MAJ barcode %s : %s", product.default_code, str(e))

    # =========================================================================
    # GETTERS Many2one
    # =========================================================================

    def _get_uom_id(self, unit_name):
        if not unit_name:
            return self.env.ref("uom.product_uom_unit").id
        uom = self.env["uom.uom"].search([("name", "=", unit_name)], limit=1)
        return uom.id if uom else self.env["uom.uom"].create({
            "name": unit_name, "relative_factor": 1.0
        }).id

    def _get_uom_ids(self, cond, unit):
        if not cond:
            return None
        factor = self._safe_float(cond)
        if factor <= 0:
            return None
        unit_id = self._get_uom_id(unit)
        name    = f"cond {cond}"
        uom     = self.env["uom.uom"].search([
            ("name", "=", name), ("relative_uom_id", "=", unit_id)
        ], limit=1)
        if uom:
            return [(6, 0, [uom.id])]
        new_uom = self.env["uom.uom"].create({
            "name": name, "relative_uom_id": unit_id, "relative_factor": factor
        })
        return [(6, 0, [new_uom.id])]

    def _get_code_inventory_id(self, name):
        if not name:
            return False
        rec = self.env["code.inventory"].search([("name", "=", name)], limit=1)
        return rec.id or self.env["code.inventory"].create({"name": name}).id

    def _get_family_id(self, name):
        if not name:
            try:
                return self.env.ref("product.product_category_all").id
            except ValueError:
                cat = self.env["product.category"].search([], limit=1)
                return cat.id or self.env["product.category"].create({"name": "Catégorie par défaut"}).id
        rec = self.env["product.category"].search([("code", "=", name)], limit=1)
        return rec.id or self.env["product.category"].create({"name": name, "code": name}).id

    def _get_sub_family_id(self, name):
        if not name:
            return False
        rec = self.env["sub.family.inventory"].search([("code", "=", name)], limit=1)
        return rec.id or self.env["sub.family.inventory"].create({"name": name, "code": name}).id

    def _get_radius_id(self, name):
        if not name:
            return False
        rec = self.env["radius.inventory"].search([("code", "=", name)], limit=1)
        return rec.id or self.env["radius.inventory"].create({"name": name, "code": name}).id

    def _get_sub_radius_id(self, name):
        if not name:
            return False
        rec = self.env["sub.radius.inventory"].search([("code", "=", name)], limit=1)
        return rec.id or self.env["sub.radius.inventory"].create({"name": name, "code": name}).id

    def _get_prod_gestion_id(self, name):
        if not name:
            return False
        rec = self.env["product.category.x3"].search([("name", "=", name)], limit=1)
        return rec.id or self.env["product.category.x3"].create({"name": name}).id

    def _get_prod_family_id(self, name):
        if not name:
            return False
        rec = self.env["product.family.x3"].search([("name", "=", name)], limit=1)
        return rec.id or self.env["product.family.x3"].create({"name": name}).id

    def _get_prod_type_id(self, name):
        if not name:
            return False
        rec = self.env["product.type.x3"].search([("name", "=", name)], limit=1)
        return rec.id or self.env["product.type.x3"].create({"name": name}).id

    def _get_prod_status_id(self, name):
        if not name:
            return False
        rec = self.env["product.status.sage"].search([("name", "=", name)], limit=1)
        return rec.id or self.env["product.status.sage"].create({"name": name}).id

    def _get_allowed_company_ids(self, item):
        company_map = {
            "01": item.get("yafdM_0"),
            "02": item.get("yafdeT_0"),
            "03": item.get("yafsyN_0"),
            "04": item.get("yafsQ_0"),
            "05": item.get("yafbsM_0"),
            "06": item.get("yafkouM_0"),
            "07": item.get("yafdoK_0"),
        }
        active_codes = [code for code, flag in company_map.items()
                        if self._verify_boolean(flag)]
        if not active_codes:
            return [(6, 0, [])]
        ids = self.env['res.company'].search(
            [('code_company', 'in', active_codes)]
        ).ids
        return [(6, 0, ids)]


# =========================================================================
# product.product — délègue à product.template
# =========================================================================

class ProductProduct(models.Model):
    _inherit = 'product.product'

    def action_import_products_external_source(self):
        return self.product_tmpl_id.action_import_products_external_source()

    def action_delete_products_no_company(self):
        return self.product_tmpl_id.action_delete_products_no_company()

    def normalize_taxes_tva_all_companies(self):
        return self.product_tmpl_id.normalize_taxes_tva_all_companies()

    def normalize_taxes_airsi_all_companies(self):
        return self.product_tmpl_id.normalize_taxes_airsi_all_companies()

    def reset_airsi_taxes_all_products(self):
        return self.product_tmpl_id.reset_airsi_taxes_all_products()
