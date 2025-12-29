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
        self.import_products()


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

    def import_products(self):
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
                        
                        # Mise à jour des fournisseurs
                        supplier_count = self._update_product_suppliers(existing, item)
                        if supplier_count > 0:
                            suppliers_added += supplier_count
                        
                        updated += 1
                    else:
                        product = self.create(vals)
                        created += 1
                        _logger.info("✅ Produit créé : %s (%s)", product.name, product.default_code)
                        self._create_pricelist_items(product, item)
                        
                        # Création des fournisseurs
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
        if not barcode or barcode in invalid_barcodes:
            barcode = False
        else:
            if self.search([("barcode", "=", barcode)], limit=1):
                _logger.warning(f"Code-barres déjà utilisé ({barcode}) — produit ignoré.")
                barcode = False

        return {
            "name": item.get("itmdeS1_0") or "Produit sans nom",
            "default_code": item.get("itmreF_0") or False,
            "barcode": barcode,
            "description": item.get("itmdeS2_0", ""),
            "list_price": self._safe_float(item.get("basprI_0")),
            "taxes_id": self._get_taxes_id(item.get("vacitM_0")),
            "supplier_taxes_id": self._get_supplier_taxes_id(item.get("vacitM_0")),
            "price_unit_ttc": self._safe_float(item.get("ypV_SAN_0")),
            "uom_id": self._get_uom_id(item.get("saU_0")),
            "prod_cond": item.get("ypcB1_0", ""),
            "weight": self._safe_float(item.get("itmweI_0")),
            "marque": item.get("ymarK_0", ""),
            "discount_ligne": item.get("yappremL_0", False),
            "airsi_tax_id": self._get_airsi_tax_id(item.get("yairsI_0")),
            "price_carton": self._safe_float(item.get("ypxcA_0")),
            "price_negoce": self._safe_float(item.get("ypxneG_0")),
            "price_ecom": self._safe_float(item.get("yglovttC_0")),
            "is_yop_demi_gros": item.get("yafdM_0", False),
            "is_yop_detail": item.get("yafdet_0", False),
            "is_synacass_ci": item.get("yafsyN_0", False),
            "is_square": item.get("yafsQ_0", False),
            "is_bassam": item.get("yafbsM_0", False),
            "is_koumassi": item.get("yafkouM_0", False),
            "code_inventory_id": self._get_code_inventory_id(item.get("yG5EMPLC_0")),
            "family_categ_id": self._get_family_id(item.get("yG5FAM_0")),
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
            # "tracking": 'lot',
        }

    # ----------------------------------------------------------
    # GESTION DES FOURNISSEURS
    # ----------------------------------------------------------
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
        
        # Mapping : (xml_id, champ_api, nom_affichage)
        pricelist_mappings = [
            ('custom_stock.basic_retailing_price', 'ypV_SAN_0', 'PRIX VENTE DE BASE TTC'),
            ('custom_stock.carton_sale_price', 'ypxcA_0', 'PRIX VENTE CARTON TTC'),
            ('custom_stock.retail_sale_price', 'ypxneG_0', 'PRIX VENTE NEGOCE TTC'),
            ('custom_stock.e_commerce_sale_price', 'yglovttC_0', 'PRIX VENTE E-COMMERCE TTC'),
        ]
        
        for xml_id, api_field, display_name in pricelist_mappings:
            price_value = self._safe_float(item.get(api_field))
            
            # Ne créer que si le prix existe et est > 0
            if not price_value or price_value <= 0:
                _logger.debug("⏭️ Prix ignoré pour %s (%s) : %.2f", 
                            product.default_code, display_name, price_value or 0)
                continue
            
            try:
                # Récupérer la liste de prix via son xml_id
                pricelist = self.env.ref(xml_id, raise_if_not_found=False)
                
                if not pricelist:
                    _logger.warning("⚠️ Liste de prix introuvable : %s", xml_id)
                    continue
                
                # Vérifier si l'item existe déjà
                existing_item = PricelistItem.search([
                    ('pricelist_id', '=', pricelist.id),
                    ('product_tmpl_id', '=', product.id),
                ], limit=1)
                
                if existing_item:
                    # Mettre à jour le prix existant
                    existing_item.write({'fixed_price': price_value})
                    _logger.info("🔄 Prix mis à jour pour %s : %s = %.2f", 
                               product.default_code, display_name, price_value)
                else:
                    # Créer une nouvelle ligne de liste de prix
                    PricelistItem.create({
                        'pricelist_id': pricelist.id,
                        'product_tmpl_id': product.id,
                        'compute_price': 'fixed',
                        'fixed_price': price_value,
                        'display_applied_on': '1_product',
                        'min_quantity': 1,
                    })
                    _logger.info("➕ Prix ajouté pour %s : %s = %.2f", 
                               product.default_code, display_name, price_value)
                    
            except Exception as e:
                _logger.error("❌ Erreur création prix pour %s (%s) : %s", 
                            product.default_code, display_name, str(e))
                
    # ----------------------------------------------------------
    # GESTION DES TAXES
    # ----------------------------------------------------------
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

    def _get_or_create_tax_group(self, amount):
        name = f"TVA {amount}%"
        tax_group = self.env["account.tax.group"].search([("name", "=", name)], limit=1)
        if tax_group:
            return tax_group
        try:
            return self.env["account.tax.group"].create({"name": name})
        except Exception:
            return self.env["account.tax.group"].search([], limit=1) or self.env["account.tax.group"].create({"name": "Taxe générique"})

    def _get_taxes_id(self, tax_code):
        amount = self._extract_tax_amount(tax_code)
        if not amount:
            return []
        tax = self.env["account.tax"].search([
            ("amount", "=", amount),
            ("amount_type", "=", "percent"),
            ("type_tax_use", "=", "sale")
        ], limit=1)
        if tax:
            return [(6, 0, [tax.id])]
        group = self._get_or_create_tax_group(amount)
        new_tax = self.env["account.tax"].create({
            "name": f"TVA {amount}%",
            "amount": amount,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "tax_group_id": group.id,
        })
        return [(6, 0, [new_tax.id])]

    def _get_supplier_taxes_id(self, tax_code):
        amount = self._extract_tax_amount(tax_code)
        if not amount:
            return []
        tax = self.env["account.tax"].search([
            ("amount", "=", amount),
            ("amount_type", "=", "percent"),
            ("type_tax_use", "=", "purchase")
        ], limit=1)
        if tax:
            return [(6, 0, [tax.id])]
        group = self._get_or_create_tax_group(amount)
        new_tax = self.env["account.tax"].create({
            "name": f"TVA Achat {amount}%",
            "amount": amount,
            "amount_type": "percent",
            "type_tax_use": "purchase",
            "tax_group_id": group.id,
        })
        return [(6, 0, [new_tax.id])]
    
    def _get_airsi_tax_id(self, tax_code):
        amount = self._extract_tax_amount(tax_code)
        if not amount:
            return False
        tax = self.env["account.tax"].search([
            ("amount", "=", amount),
            ("amount_type", "=", "percent"),
            ("type_tax_use", "=", "sale")
        ], limit=1)
        if tax:
            return tax.id
        group = self._get_or_create_tax_group(amount)
        new_tax = self.env["account.tax"].create({
            "name": f"TVA AIRSI {amount}%",
            "amount": amount,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "tax_group_id": group.id,
        })
        return new_tax.id


    # ----------------------------------------------------------
    # GETTERS DES LIENS "Many2one" (catégories, familles, etc.)
    # ----------------------------------------------------------
    def _get_uom_id(self, unit_name):
        if not unit_name:
            return self.env.ref("uom.product_uom_unit").id
        uom = self.env["uom.uom"].search([("name", "ilike", unit_name)], limit=1)
        return uom.id or self.env.ref("uom.product_uom_unit").id

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


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def import_products(self):
        return self.product_tmpl_id.import_products()