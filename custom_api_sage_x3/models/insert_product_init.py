import requests
import logging as logger
from odoo import fields, models, api
from odoo.exceptions import UserError
import time
import gc

_logger = logger.getLogger(__name__)

BASE_URL = "http://172.16.2.150:8030"
AUTH_URL = f"{BASE_URL}/api/Auth/login"
ITEMS_URL = f"{BASE_URL}/api/Items"
USERNAME = "odoo"
PASSWORD = "InterfaceX3_Odoo"

MAX_RETRIES = 3
PAGE_SIZE = 100
COMMIT_STEP = 20
MAX_PAGES = 1000
TIMEOUT = 30


class ProductTemplateImport(models.Model):
    _inherit = "product.template"

    # @job
    def import_products_job(self):
        self.action_import_from_external_source()

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
            }
        }


    def safe_get(self, url, headers, params, timeout=TIMEOUT):
        """Appel GET avec retry et timeout"""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
                if response.status_code in (200, 201):
                    return response
                _logger.warning("⚠️ Statut HTTP inattendu (tentative %s) : %s", attempt, response.status_code)
            except requests.exceptions.RequestException as e:
                _logger.warning("⚠️ Exception réseau (tentative %s) : %s", attempt, str(e))
            time.sleep(5)
        raise UserError("Échec de récupération des données après plusieurs tentatives.")

    def action_import_from_external_source(self):
        """Importation des produits depuis l'API SAGE X3 avec gestion d'erreurs et commits réguliers."""
        try:
            auth_data = {"username": USERNAME, "password": PASSWORD}
            response = requests.post(AUTH_URL, json=auth_data, timeout=15)
            if response.status_code not in (200, 201):
                raise UserError(f"Erreur d'authentification : {response.text}")

            token = response.json().get("token")
            if not token:
                raise UserError("Token d'authentification manquant dans la réponse.")

            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            all_items = []
            page = 1
            start_time = time.time()

            while page <= MAX_PAGES:
                if time.time() - start_time > 300:
                    _logger.warning("⏱️ Import interrompu : durée maximale atteinte")
                    break

                params = {"pageNumber": page, "pageSize": PAGE_SIZE}
                response = self.safe_get(ITEMS_URL, headers, params)
                data = response.json()
                items = data.get("items", [])
                all_items.extend(items)
                _logger.info("📦 Page %s récupérée (%s produits)", page, len(items))

                if not data.get("hasNextPage", False):
                    break
                page += 1

            created, updated, skipped, errors, price_updated, suppliers_added = 0, 0, 0, 0, 0, 0

            for idx, item in enumerate(all_items, start=1):
                try:
                    vals = self.prepare_product_values(item)
                    if not vals.get("default_code"):
                        _logger.warning("⚠️ Produit ignoré sans default_code : %s", vals.get("name"))
                        skipped += 1
                        continue
                    if "SF" in str(vals.get("default_code", "")).upper():
                        _logger.info("⏭️ Produit ignoré (code SF) : %s", vals.get("default_code"))
                        skipped += 1
                        continue

                    existing = self.search([("default_code", "=", vals["default_code"])], limit=1)

                    if existing:
                        new_list_price = vals.get("list_price", 0)
                        if existing.list_price != new_list_price:
                            old_price = existing.list_price
                            existing.write({'list_price': new_list_price})
                            _logger.info("💰 Prix mis à jour pour %s : %.2f → %.2f",
                                         existing.default_code, old_price, new_list_price)
                            price_updated += 1

                        _logger.info("🔄 Produit existant : %s - Mise à jour des listes de prix", existing.name)
                        self._create_pricelist_items(existing, item)
                        supplier_count = self._update_product_suppliers(existing, item)
                        if supplier_count > 0:
                            suppliers_added += supplier_count
                        
                        updated += 1
                    else:
                        product = self.create(vals)
                        created += 1
                        _logger.info("✅ Produit créé : %s (%s)", product.name, product.default_code)
                        self._create_pricelist_items(product, item)
                        supplier_count = self._update_product_suppliers(product, item)
                        if supplier_count > 0:
                            suppliers_added += supplier_count

                    if idx % COMMIT_STEP == 0:
                        self.env.cr.commit()
                        gc.collect()
                        _logger.info("💾 Commit effectué après %s produits", idx)

                except Exception as e:
                    errors += 1
                    _logger.exception("❌ Erreur produit %s : %s", item.get("itmdeS1_0"), str(e))
                    try:
                        if not self.env.cr.closed:
                            self.env.cr.rollback()
                            self.env.invalidate_all()
                        else:
                            _logger.warning("⚠️ Curseur déjà fermé, impossible de rollback")
                        # Recréer un environnement propre pour continuer
                        self = self.env['product.template'].sudo()
                    except Exception as rollback_error:
                        _logger.warning("⚠️ Rollback échoué : %s", str(rollback_error))

            self.env.cr.commit()
            _logger.info("=" * 50)
            _logger.info("=== RÉSUMÉ IMPORTATION PRODUITS ===")
            _logger.info("=" * 50)
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
        
    # ----------------------------------------------------------
    # OUTILS
    # ----------------------------------------------------------
    def _safe_float(self, value, default=0.0):
        if not value:
            return default
        try:
            return float(str(value).replace(",", ".").replace(" ", ""))
        except (ValueError, TypeError):
            return default
    
    def _safe_string(self, value, default=""):
        """Retourne une chaîne sécurisée"""
        if not value or str(value).strip() == "":
            return default
        return str(value).strip()

    def prepare_product_values(self, item):
        """Prépare le dictionnaire de valeurs produit pour la création."""
        barcode = item.get("saN_CB_0", "").strip()
        invalid_barcodes = ["", "0", "00", "000", "0000", "00000"]
        
        # Si pas de code-barres ou invalide
        if not barcode or barcode in invalid_barcodes:
            barcode = False
        else:
            # CORRECTION GS1 : Si c'est un code à 13 chiffres commençant par 27 et finissant par 0000000
            if len(barcode) == 13 and barcode.startswith('27') and barcode.endswith('0000000'):
                old_barcode = barcode
                barcode = self.fix_gs1_barcode(barcode)
                _logger.info("🔧 Code-barres GS1 corrigé : %s → %s", old_barcode, barcode)
            
            # Vérifier si le code-barres (corrigé ou non) existe déjà
            existing = self.search([("barcode", "=", barcode)], limit=1)
            if existing:
                _logger.warning("⚠️ Code-barres déjà utilisé (%s) par %s — barcode ignoré", 
                            barcode, existing.default_code)
                barcode = False

        vals = {
            "name": item.get("itmdeS1_0") or "Produit sans nom",
            "default_code": item.get("itmreF_0") or False,
            "barcode": barcode,
            "description": item.get("itmdeS2_0", ""),
            "list_price": self._get_ht_price(item.get("ypV_SAN_0"), item.get("vacitM_0")),
            "taxes_id": self._get_taxes_id(item.get("vacitM_0")),
            # "supplier_taxes_id": self._get_supplier_taxes_id(item.get("vacitM_0")),
            "price_unit_ttc": self._safe_float(item.get("ypV_SAN_0")),
            "uom_id": self._get_uom_id(item.get("saU_0")),
            "prod_cond": item.get("ypcB1_0", ""),
            "weight": self._safe_float(item.get("itmweI_0")),
            "marque": item.get("ymarK_0", ""),
            "discount_ligne": item.get("yappremL_0", False),
            "airsi_taxes_id": self._get_airsi_taxes_id(item.get("yairsI_0")),
            "price_catalog": self._safe_float(item.get("basprI_0")),
            "price_carton": self._safe_float(item.get("ypxcA_0")),
            "price_negoce": self._safe_float(item.get("ypxneG_0")),
            "price_ecom": self._safe_float(item.get("yglovttC_0")),
            "is_yop_demi_gros": self._verify_boolean(item.get("yafdM_0")),
            "is_yop_detail": self._verify_boolean(item.get("yafdeT_0")),
            "is_synacass_ci": self._verify_boolean(item.get("yafsyN_0")),
            "is_square": self._verify_boolean(item.get("yafsQ_0")),
            "is_bassam": self._verify_boolean(item.get("yafbsM_0")),
            "is_koumassi": self._verify_boolean(item.get("yafkouM_0")),
            "allowed_company_ids": self._get_allowed_company_ids(item),
            "code_inventory_id": self._get_code_inventory_id(item.get("yG5EMPLC_0")),
            "family_categ_id": self._get_family_id(item.get("yG5FAM_0")),
            "categ_id": self._get_family_id(item.get("yG5FAM_0")),
            "s_family_id": self._get_sub_family_id(item.get("yG5SFAM_0")),
            "radius_id": self._get_radius_id(item.get("yG5RAY_0")),
            "s_radius_id": self._get_sub_radius_id(item.get("yG5SRAY_0")),
            "cat_gestion_id": self._get_prod_gestion_id(item.get("tclcoD_0")),
            "prod_family_x3_id": self._get_prod_family_id(item.get("tsicoD_0")),
            "prod_type_x3_id": self._get_prod_type_id(item.get("yG5TYPE_0")),
            "prod_status_x3_id": self._get_prod_status_id(item.get("yG5STAT_0")),
            "type": "consu",
            "active": True,
            "sale_ok": True,
            "purchase_ok": True,
            "available_in_pos": True,
            "is_storable": True,
        }
        uom_ids = self._get_uom_ids(item.get("ypcB1_0"), item.get("saU_0"))
        if uom_ids is not None:
            vals["uom_ids"] = uom_ids
        
        return vals

    # ----------------------------------------------------------
    # GESTION DES FOURNISSEURS
    # ----------------------------------------------------------
    def _verify_boolean(self, value):
        """Verifier si c'est un false (0, 1) ou true (2) ."""
        vals = self._safe_float(value)
        if vals == 2:
            return True
        elif vals in [0, 1]:
            return False
        else:
            _logger.warning("⚠️ Valeur non reconnue pour boolean : %s", value)
            return False
    

    def _get_ht_price(self, price, tax):
        """Calcule le prix HT à partir du prix TTC et du taux de taxe extrait du code taxe."""
        price_ttc = self._safe_float(price)
        tax_amount = self._extract_tax_amount(tax)
        
        if tax_amount > 0:
            price_ht = price_ttc / (1 + tax_amount / 100)
            return round(price_ht, 2)
        else:
            return price_ttc 
        
    def _update_product_suppliers(self, product, item):
        """
        Crée ou met à jour les fournisseurs d'un produit
        
        Args:
            product: Enregistrement product.template
            item: Données de l'API SAGE X3
            
        Returns:
            Nombre de fournisseurs ajoutés/mis à jour
        """
        supplier_code = self._safe_string(item.get("yG5FRS_0"))
        
        if not supplier_code:
            _logger.debug("⏭️ Pas de fournisseur pour le produit %s", product.default_code)
            return 0
        
        try:
            SupplierInfo = self.env['product.supplierinfo']
            
            # Rechercher le partenaire fournisseur par son code (ref ou customer_id)
            supplier = self.env['res.partner'].search([
                '|',
                ('ref', '=', supplier_code),
                ('name', '=', supplier_code),
                ('supplier_rank', '>', 0)  # Doit être marqué comme fournisseur
            ], limit=1)
            
            if not supplier:
                # Créer un fournisseur basique si introuvable
                supplier = self.env['res.partner'].create({
                    'name': supplier_code,
                    'ref': supplier_code,
                    'supplier_rank': 1,
                    'is_company': True,
                })
                _logger.info("➕ Fournisseur créé : %s (%s)", supplier.name, supplier_code)
            
            # Vérifier si une ligne fournisseur existe déjà
            existing_supplierinfo = SupplierInfo.search([
                ('product_tmpl_id', '=', product.id),
                ('partner_id', '=', supplier.id)
            ], limit=1)
            
            if existing_supplierinfo:
                _logger.debug("🔄 Ligne fournisseur existante pour %s", product.default_code)
                return 0
            else:
                # Créer la ligne fournisseur
                SupplierInfo.create({
                    'partner_id': supplier.id,
                    'product_tmpl_id': product.id,
                    'min_qty': 1.0,
                    'primary': True,
                    'currency_id': self.env.company.currency_id.id,
                })
                _logger.info("🏭 Fournisseur ajouté au produit %s : %s", 
                           product.default_code, supplier.name)
                return 1
                
        except Exception as e:
            _logger.error("❌ Erreur ajout fournisseur pour %s : %s", 
                        product.default_code, str(e))
            return 0


    def _create_pricelist_items(self, product, item):
        """Crée les lignes de liste de prix pour un produit."""
        PricelistItem = self.env['product.pricelist.item']

        # Récupération de la taxe depuis l'API
        tax_code = item.get('vacitM_0')

        # Mapping : (xml_id, champ_api, nom_affichage, multiplicateur)
        pricelist_mappings = [
            ('custom_stock.basic_retailing_price', 'ypV_SAN_0', 'PRIX VENTE DE BASE TTC',  1.0),
            ('custom_stock.catalog_sale_price',    'basprI_0',  'PRIX VENTE CATALOGUE',     1.0),
            ('custom_stock.carton_sale_price',     'ypxcA_0',   'PRIX VENTE CARTON TTC',    1.0),
            ('custom_stock.retail_sale_price',     'ypxneG_0',  'PRIX VENTE NEGOCE TTC',    1.0),
            ('custom_stock.e_commerce_sale_price', 'yglovttC_0','PRIX VENTE E-COMMERCE TTC',1.0),
            ('custom_stock.gm_sale_price',         'basprI_0',  'TARIF GMS',                 1.05),
            ('custom_stock.rh_sale_price',         'basprI_0',  'TARIF RHF',                 1.02),
            ('custom_stock.st_sale_price',         'basprI_0',  'TARIF STATION',                 1.01),
        ]

        # Mettre à jour les champs de prix sur le produit (une seule fois, hors boucle)
        product.write({
            "list_price":      self._get_ht_price(item.get("ypV_SAN_0"), tax_code),
            "price_unit_ttc":  self._safe_float(item.get("ypV_SAN_0")),
            "price_catalog":   self._safe_float(item.get("basprI_0")),
            "price_carton":    self._safe_float(item.get("ypxcA_0")),
            "price_negoce":    self._safe_float(item.get("ypxneG_0")),
            "price_ecom":      self._safe_float(item.get("yglovttC_0")),
            "price_gm":        self._safe_float(item.get("basprI_0")) * 1.05,
            "price_rh":        self._safe_float(item.get("basprI_0")) * 1.02,
            "price_st":        self._safe_float(item.get("basprI_0")) * 1.01,
            "is_yop_demi_gros": self._verify_boolean(item.get("yafdM_0")),
            "is_yop_detail": self._verify_boolean(item.get("yafdeT_0")),
            "is_synacass_ci": self._verify_boolean(item.get("yafsyN_0")),
            "is_square": self._verify_boolean(item.get("yafsQ_0")),
            "is_bassam": self._verify_boolean(item.get("yafbsM_0")),
            "is_koumassi": self._verify_boolean(item.get("yafkouM_0")),
            "allowed_company_ids": self._get_allowed_company_ids(item),
        })

        for xml_id, api_field, display_name, multiplier in pricelist_mappings:
            price_value_ttc = self._safe_float(item.get(api_field))

            # Ne créer que si le prix existe et est > 0
            if not price_value_ttc or price_value_ttc <= 0:
                _logger.debug("⏭️ Prix ignoré pour %s (%s) : %.2f",
                            product.default_code, display_name, price_value_ttc or 0)
                continue

            # Conversion TTC → HT puis application du multiplicateur
            price_value = round(self._get_ht_price(price_value_ttc, tax_code) * multiplier, 2)
            _logger.debug("💱 %s | TTC: %.2f → HT: %.2f × %.2f = %.2f (taxe: %s)",
                        display_name, price_value_ttc,
                        price_value / multiplier, multiplier, price_value, tax_code)

            try:
                pricelist = self.env.ref(xml_id, raise_if_not_found=False)

                if not pricelist:
                    _logger.warning("⚠️ Liste de prix introuvable : %s", xml_id)
                    continue

                existing_item = PricelistItem.search([
                    ('pricelist_id', '=', pricelist.id),
                    ('product_tmpl_id', '=', product.id),
                ], limit=1)

                if existing_item:
                    existing_item.write({'fixed_price': price_value})
                else:
                    PricelistItem.create({
                        'pricelist_id': pricelist.id,
                        'product_tmpl_id': product.id,
                        'compute_price': 'fixed',
                        'fixed_price': price_value,
                        'display_applied_on': '1_product',
                        'min_quantity': 1,
                    })

            except Exception as e:
                _logger.error("❌ Erreur création prix pour %s (%s) : %s",
                            product.default_code, display_name, str(e))
                
    # ----------------------------------------------------------
    # GESTION DES TAXES
    # ----------------------------------------------------------
    # def _extract_tax_amount(self, tax_code):
    #     import re
    #     if not tax_code:
    #         return 0.0
    #     try:
    #         return float(tax_code)
    #     except ValueError:
    #         pass
    #     numbers = re.findall(r"\d+\.?\d*", str(tax_code))
    #     return float(numbers[0]) if numbers else 0.0

    # def _get_or_create_tax_group(self, amount):
    #     name = f"TVA {amount}%"
    #     tax_group = self.env["account.tax.group"].search([("name", "=", name)], limit=1)
    #     if tax_group:
    #         return tax_group
    #     try:
    #         return self.env["account.tax.group"].create({"name": name})
    #     except Exception:
    #         return self.env["account.tax.group"].search([], limit=1) or self.env["account.tax.group"].create({"name": "Taxe générique"})

    # def _get_taxes_id(self, tax_code):
    #     amount = self._extract_tax_amount(tax_code)
    #     if not amount:
    #         return []
    #     tax = self.env["account.tax"].search([
    #         ("amount", "=", amount),
    #         ("amount_type", "=", "percent"),
    #         ("type_tax_use", "=", "sale")
    #     ], limit=1)
    #     if tax:
    #         return [(6, 0, [tax.id])]
    #     group = self._get_or_create_tax_group(amount)
    #     new_tax = self.env["account.tax"].create({
    #         "name": f"TVA {amount}%",
    #         "amount": amount,
    #         "amount_type": "percent",
    #         "type_tax_use": "sale",
    #         "tax_group_id": group.id,
    #     })
    #     return [(6, 0, [new_tax.id])]

    # def _get_supplier_taxes_id(self, tax_code):
    #     amount = self._extract_tax_amount(tax_code)
    #     if not amount:
    #         return []
    #     tax = self.env["account.tax"].search([
    #         ("amount", "=", amount),
    #         ("amount_type", "=", "percent"),
    #         ("type_tax_use", "=", "purchase")
    #     ], limit=1)
    #     if tax:
    #         return [(6, 0, [tax.id])]
    #     group = self._get_or_create_tax_group(amount)
    #     new_tax = self.env["account.tax"].create({
    #         "name": f"TVA Achat {amount}%",
    #         "amount": amount,
    #         "amount_type": "percent",
    #         "type_tax_use": "purchase",
    #         "tax_group_id": group.id,
    #     })
    #     return [(6, 0, [new_tax.id])]
    
    # def _get_airsi_tax_id(self, tax_code):
    #     amount = self._extract_tax_amount(tax_code)
    #     if not amount:
    #         return False
    #     tax = self.env["account.tax"].search([
    #         ("amount", "=", amount),
    #         ("amount_type", "=", "percent"),
    #         ("type_tax_use", "=", "sale")
    #     ], limit=1)
    #     if tax:
    #         return tax.id
    #     group = self._get_or_create_tax_group(amount)
    #     new_tax = self.env["account.tax"].create({
    #         "name": f"TVA AIRSI {amount}%",
    #         "amount": amount,
    #         "amount_type": "percent",
    #         "type_tax_use": "sale",
    #         "tax_group_id": group.id,
    #     })
    #     return new_tax.id

    def _extract_tax_amount(self, tax_code):
        import re
        if not tax_code:
            return 0.0
        try:
            return float(tax_code)
        except ValueError:
            pass
        numbers = re.findall(r"\d+\.?\d*", str(tax_code))
        return float(numbers[0]) if numbers else 0.0

    def _get_or_create_tax_group(self, amount, company):
        name = f"TVA {amount}%"
        env = self.env['account.tax.group'].with_company(company)
        tax_group = env.search([
            ("name", "=", name),
            ("company_id", "=", company.id)
        ], limit=1)
        if tax_group:
            return tax_group
        try:
            return env.create({"name": name, "company_id": company.id})
        except Exception:
            return env.search([("company_id", "=", company.id)], limit=1) or \
                env.create({"name": "Taxe générique", "company_id": company.id})

    def _get_or_create_tax(self, name, amount, company):
        """Cherche ou crée une taxe pour une société donnée."""
        env_tax = self.env['account.tax'].with_company(company)
        tax = env_tax.search([
            ("amount", "=", amount),
            ("amount_type", "=", "percent"),
            ("type_tax_use", "=", "sale"),
            ("company_id", "=", company.id),
        ], limit=1)
        if tax:
            return tax
        group = self._get_or_create_tax_group(amount, company)
        return env_tax.create({
            "name": name,
            "amount": amount,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "tax_group_id": group.id,
            "company_id": company.id,
        })

    def _get_taxes_id(self, tax_code):
        """Crée la TVA pour toutes les sociétés → Many2many (6, 0, [...])"""
        amount = self._extract_tax_amount(tax_code)
        if not amount:
            return []

        all_companies = self.env['res.company'].search([])
        tax_ids = []

        for company in all_companies:
            tax = self._get_or_create_tax(f"TVA {amount}%", amount, company)
            tax_ids.append(tax.id)

        return [(6, 0, tax_ids)]

    def _get_airsi_taxes_id(self, tax_code):
        """AIRSI en Many2many → même logique multi-société"""
        amount = self._extract_tax_amount(tax_code)
        if not amount:
            return []

        all_companies = self.env['res.company'].search([])
        tax_ids = []

        for company in all_companies:
            tax = self._get_or_create_tax(f"TVA AIRSI {amount}%", amount, company)
            tax_ids.append(tax.id)

        return [(6, 0, tax_ids)]


    # ----------------------------------------------------------
    # GETTERS DES LIENS "Many2one" (catégories, familles, etc.)
    # ----------------------------------------------------------
    def _get_uom_id(self, unit_name):
        if not unit_name:
            return self.env.ref("uom.product_uom_unit").id
        uom = self.env["uom.uom"].search([("name", "ilike", unit_name)], limit=1)
        if uom:
            return uom.id
        else:
            new_uom = self.env["uom.uom"].create({
                "name": unit_name,
                "relative_factor": 1.0,
            })
            return new_uom.id
    
    def _get_uom_ids(self, cond, unit):
        # ✅ Si pas de condition, ne pas renseigner le champ
        if not cond:
            return None

        factor = self._safe_float(cond)
        if factor <= 0:
            return None

        unit_id = self._get_uom_id(unit)
        name = f"cond {cond}"

        uom = self.env["uom.uom"].search([
            ("name", "ilike", name),
            ("relative_uom_id", "=", unit_id),
        ], limit=1)

        if uom:
            return [(6, 0, [uom.id])]
        else:
            new_uom = self.env["uom.uom"].create({
                "name": name,
                "relative_uom_id": unit_id,
                "relative_factor": factor,
            })
            return [(6, 0, [new_uom.id])]

    def _get_code_inventory_id(self, name):
        if not name:
            default = self.env["code.inventory"].search([], limit=1)
            return default.id or self.env["code.inventory"].create({"name": "Non défini"}).id
        rec = self.env["code.inventory"].search([("name", "ilike", name)], limit=1)
        return rec.id or self.env["code.inventory"].create({"name": name}).id

    def _get_family_id(self, name):
        if not name:
            try:
                return self.env.ref("product.product_category_all").id
            except ValueError:
                cat = self.env["product.category"].search([], limit=1)
                return cat.id or self.env["product.category"].create({"name": "Catégorie par défaut"}).id
        rec = self.env["product.category"].search([("code", "ilike", name)], limit=1)
        return rec.id or self.env["product.category"].create({"name": name, "code": name}).id

    def _get_sub_family_id(self, name):
        if not name:
            return False
        rec = self.env["sub.family.inventory"].search([("name", "ilike", name)], limit=1)
        return rec.id or self.env["sub.family.inventory"].create({"name": name}).id

    def _get_radius_id(self, name):
        if not name:
            return False
        rec = self.env["radius.inventory"].search([("name", "ilike", name)], limit=1)
        return rec.id or self.env["radius.inventory"].create({"name": name}).id

    def _get_sub_radius_id(self, name):
        if not name:
            return False
        rec = self.env["sub.radius.inventory"].search([("name", "ilike", name)], limit=1)
        return rec.id or self.env["sub.radius.inventory"].create({"name": name}).id

    def _get_prod_gestion_id(self, name):
        if not name:
            return False
        rec = self.env["product.category.x3"].search([("name", "ilike", name)], limit=1)
        return rec.id or self.env["product.category.x3"].create({"name": name}).id

    def _get_prod_family_id(self, name):
        if not name:
            return False
        rec = self.env["product.family.x3"].search([("name", "ilike", name)], limit=1)
        return rec.id or self.env["product.family.x3"].create({"name": name}).id

    def _get_prod_type_id(self, name):
        if not name:
            return False
        rec = self.env["product.type.x3"].search([("name", "ilike", name)], limit=1)
        return rec.id or self.env["product.type.x3"].create({"name": name}).id

    def _get_prod_status_id(self, name):
        if not name:
            return False
        rec = self.env["product.status.sage"].search([("name", "ilike", name)], limit=1)
        return rec.id or self.env["product.status.sage"].create({"name": name}).id

    def fix_gs1_barcode(self,current_barcode):
        """
        Calcule la clé de contrôle GS1 et remplace le dernier chiffre.
        
        :param current_barcode: str ou int, le code actuel (ex: '2715180000000')
        :return: str, le code barres corrigé avec la bonne clé GS1
        """
        # Convertir en chaîne et nettoyer
        barcode_str = str(current_barcode).strip()
        
        # Vérifier que la longueur est correcte (13 caractères pour EAN-13)
        if len(barcode_str) != 13:
            _logger.info(f"Attention : Le code {barcode_str} n'a pas 13 caractères.")
            return barcode_str

        # Extraire les 12 premiers chiffres (le préfixe + code article + padding)
        base_code = barcode_str[:12]
        
        even_sum = 0
        odd_sum = 0
        
        for i in range(12):
            digit = int(base_code[i])
            if (i + 1) % 2 == 0:
                even_sum += digit
            else:
                odd_sum += digit
                
        total = (even_sum * 3) + odd_sum
        check_digit = (10 - (total % 10)) % 10
        new_barcode = base_code + str(check_digit)
        
        return new_barcode
    
    def update_products_barcodes(self, product, item):
        """
        Met à jour les codes barres des produits pour corriger la clé GS1.
        
        Args:
            product: Enregistrement product.template à mettre à jour
            item: Données de l'API SAGE X3
        """
        barcode = self._safe_string(item.get("saN_CB_0"))
        
        # Vérifier que le barcode n'est pas vide et fait bien 13 caractères
        if not barcode or len(barcode) != 13:
            return
        
        # Vérifier si c'est un code-barres à corriger (commence par 27 et finit par 0000000)
        if barcode.startswith('27') and barcode.endswith('0000000'):
            old_barcode = barcode
            new_barcode = self.fix_gs1_barcode(old_barcode)
            
            if old_barcode != new_barcode:
                try:
                    # Vérifier si le nouveau code-barres n'est pas déjà utilisé par un autre produit
                    existing_with_new_barcode = self.search([
                        ("barcode", "=", new_barcode),
                        ("id", "!=", product.id)
                    ], limit=1)
                    
                    if existing_with_new_barcode:
                        _logger.warning(
                            "⚠️ Le code-barres corrigé %s est déjà utilisé par le produit %s. "
                            "Conservation du code-barres original %s pour %s",
                            new_barcode, existing_with_new_barcode.default_code,
                            old_barcode, product.default_code
                        )
                        return
                    
                    # Mettre à jour le code-barres du produit
                    product.write({'barcode': new_barcode})
                    _logger.info(
                        "✅ Code-barres corrigé pour %s : %s → %s",
                        product.default_code, old_barcode, new_barcode
                    )
                    
                except Exception as e:
                    _logger.error(
                        "❌ Erreur mise à jour code-barres pour %s : %s",
                        product.default_code, str(e)
                    )


    def _get_allowed_company_ids(self, item):
        # Mapping code société → paramètre booléen
        company_map = {
            "01": item.get("yafdM_0"), # is_yop_demi_gros
            "02": item.get("yafdeT_0"), # is_yop_detail
            "03": item.get("yafsyN_0"), # is_synacass_ci
            "04": item.get("yafsQ_0"), # is_square
            "05": item.get("yafbsM_0"), # is_bassam
            "06": item.get("yafkouM_0"), # is_koumassi
            "07": item.get("abobo"), # is_abobo
        }

        # Codes des sociétés cochées
        active_codes = [code for code, flag in company_map.items() if self._verify_boolean(flag)]

        if not active_codes:
            return None 
        company_ids = self.env['res.company'].search(
            [('code_company', 'in', active_codes)]
        ).ids

        return [(6, 0, company_ids)]
    

class ProductProduct(models.Model):
    _inherit = 'product.product'

    def action_import_from_external_source(self):
        return self.product_tmpl_id.action_import_from_external_source()