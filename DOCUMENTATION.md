# Documentation Technique — Projet SANGEL (Odoo 19)

**Version** : 19.0  
**Auteur** : Partenaires Succes / Adama KONE  
**Date** : Mai 2026  
**Licence** : LGPL-3 / AGPL-3

---

## Table des matières

1. [Vue d'ensemble du projet](#1-vue-densemble-du-projet)
2. [Architecture générale](#2-architecture-générale)
3. [Inventaire des modules](#3-inventaire-des-modules)
4. [Détail des modules](#4-détail-des-modules)
   - 4.1 [custom_pos — Point de Vente personnalisé](#41-custom_pos--point-de-vente-personnalisé)
   - 4.2 [custom_sales — Ventes et promotions](#42-custom_sales--ventes-et-promotions)
   - 4.3 [custom_stock — Gestion des stocks](#43-custom_stock--gestion-des-stocks)
   - 4.4 [custom_loyalty — Programme de fidélité](#44-custom_loyalty--programme-de-fidélité)
   - 4.5 [custom_food_credit — Crédit alimentaire](#45-custom_food_credit--crédit-alimentaire)
   - 4.6 [custom_api_sage_x3 — Intégration SAGE X3](#46-custom_api_sage_x3--intégration-sage-x3)
   - 4.7 [custom_purchase — Achats](#47-custom_purchase--achats)
   - 4.8 [custom_account — Comptabilité](#48-custom_account--comptabilité)
   - 4.9 [custom_partner — Partenaires](#49-custom_partner--partenaires)
   - 4.10 [custom_reports — Rapports PDF](#410-custom_reports--rapports-pdf)
   - 4.11 [custom_reliquat_report — Rapport de reliquats](#411-custom_reliquat_report--rapport-de-reliquats)
   - 4.12 [custom_multi_barcode_for_products — Multi-codes-barres](#412-custom_multi_barcode_for_products--multi-codes-barres)
   - 4.13 [custom_price_change_tracker — Suivi des prix](#413-custom_price_change_tracker--suivi-des-prix)
   - 4.14 [cfao_dashboard_report — Tableau de bord CFAO](#414-cfao_dashboard_report--tableau-de-bord-cfao)
   - 4.15 [dashboard_management_administration — Dashboard Admin](#415-dashboard_management_administration--dashboard-admin)
   - 4.16 [fne_certification — Certification FNE](#416-fne_certification--certification-fne)
   - 4.17 [stock_avco_correction — Correction AVCO](#417-stock_avco_correction--correction-avco)
   - 4.18 [pos_history_import — Import historique POS](#418-pos_history_import--import-historique-pos)
   - 4.19 [hide_menu_user — Masquage de menus](#419-hide_menu_user--masquage-de-menus)
   - 4.20 [queue_job — File de travaux asynchrones](#420-queue_job--file-de-travaux-asynchrones)
5. [Modèles de données clés](#5-modèles-de-données-clés)
6. [Workflows métier](#6-workflows-métier)
7. [Sécurité et droits d'accès](#7-sécurité-et-droits-daccès)
8. [APIs et intégrations externes](#8-apis-et-intégrations-externes)
9. [Personnalisations du POS (JavaScript)](#9-personnalisations-du-pos-javascript)
10. [Rapports et tableaux de bord](#10-rapports-et-tableaux-de-bord)
11. [Tâches planifiées (Crons)](#11-tâches-planifiées-crons)
12. [Dépendances externes Python](#12-dépendances-externes-python)
13. [Paramètres système](#13-paramètres-système)

---

## 1. Vue d'ensemble du projet

Le projet SANGEL est une suite de **24 modules Odoo 19 personnalisés** destinée à la gestion complète d'une enseigne de distribution multi-sites. Elle couvre :

- La **caisse (POS)** avec authentification sécurisée, taxes automatiques, multi-devises et fidélité
- La **gestion des stocks** avec inventaires physiques, transferts inter-sociétés et pilotage de coûts AVCO
- Les **ventes et promotions** avec règles tarifaires dynamiques et gestion de remises
- Les **achats** avec synchronisation vers l'ERP SAGE X3
- La **fidélité clients** avec familles de points configurables
- Le **crédit alimentaire** pour les employés
- La **certification FNE** des factures
- Des **tableaux de bord** et **rapports PDF** élaborés

---

## 2. Architecture générale

```
addons-sangel-19/
├── custom_pos/                    # POS — cœur caisse
├── custom_sales/                  # Ventes, promotions, tarifs
├── custom_stock/                  # Stocks, inventaires, inter-sociétés
├── custom_loyalty/                # Fidélité clients
├── custom_food_credit/            # Crédit alimentaire employés
├── custom_api_sage_x3/            # Intégration ERP SAGE X3
├── custom_purchase/               # Achats personnalisés
├── custom_account/                # Comptabilité
├── custom_partner/                # Partenaires/clients
├── custom_reports/                # Rapports PDF (20+)
├── custom_reliquat_report/        # Rapports de reliquats
├── custom_multi_barcode_for_products/  # Multi-codes-barres
├── custom_price_change_tracker/   # Suivi historique des prix
├── cfao_dashboard_report/         # Tableau de bord multi-société
├── dashboard_management_administration/  # Dashboard admin
├── fne_certification/             # Certification fiscale FNE
├── stock_avco_correction/         # Correction coûts AVCO
├── pos_history_import/            # Import historique POS
├── hide_menu_user/                # Masquage de menus par utilisateur
└── queue_job/                     # File de tâches asynchrones (OCA)
```

**Dépendances inter-modules** (principales) :

```
custom_pos ← custom_loyalty ← custom_food_credit
custom_stock ← custom_sales ← custom_purchase
custom_api_sage_x3 ← custom_stock, custom_partner, custom_food_credit
dashboard_management_administration ← custom_api_sage_x3, custom_stock, custom_pos
custom_reports ← custom_stock, custom_sales, dashboard_management_administration
```

---

## 3. Inventaire des modules

| Module | Version | Rôle principal |
|---|---|---|
| `custom_pos` | 1.0.0 | POS : authentification, taxes, multi-devises, clôture |
| `custom_sales` | 1.0.0 | Promotions, tarifs, remises globales POS |
| `custom_stock` | latest | Inventaires physiques, transferts, AVCO |
| `custom_loyalty` | 1.2.0 | Familles de fidélité, points POS |
| `custom_food_credit` | 1.1.0 | Crédit alimentaire employés |
| `custom_api_sage_x3` | 1.0 | Synchronisation avec SAGE X3 |
| `custom_purchase` | 1.0.0 | Achats, réapprovisionnement |
| `custom_account` | latest | Budgets analytiques, comptabilité |
| `custom_partner` | 1.1.0 | Extensions partenaires |
| `custom_reports` | latest | Rapports PDF (20+) |
| `custom_reliquat_report` | latest | Taux de satisfaction commandes |
| `custom_multi_barcode_for_products` | latest | Multi-codes-barres produits |
| `custom_price_change_tracker` | latest | Historique et alertes de prix |
| `cfao_dashboard_report` | 19.0.1.0.0 | Dashboard ventes/marges multi-société |
| `dashboard_management_administration` | latest | Dashboard admin avec graphiques JS |
| `fne_certification` | 1.0 | Certification fiscale FNE |
| `stock_avco_correction` | 19.0.1.0.0 | Correction AVCO post-migration |
| `pos_history_import` | 19.0.1.0.0 | Import Excel historique POS |
| `hide_menu_user` | 19.0.1.0.0 | Masquage de menus par utilisateur |
| `queue_job` | 19.0.1.1.0 | File d'attente de tâches (OCA) |

---

## 4. Détail des modules

### 4.1 `custom_pos` — Point de Vente personnalisé

**Objectif** : Personnalisation complète de la caisse Odoo 19 pour les besoins métier SANGEL.

**Modèles** :

| Modèle | Description |
|---|---|
| `pos.manager.code` | Codes d'authentification manager pour les opérations sensibles |
| `pos.order` (hérit.) | Override de `write()` pour autoriser la modification du paiement sur commandes imprimées |
| `pos.config` (hérit.) | Configuration étendue de la caisse |
| `pos.session` (hérit.) | Rapports de clôture (cloture_caisse, rapport_validation) |
| `pos.payment_method` (hérit.) | Méthodes de paiement étendues |
| `product.template` (hérit.) | Paramètres POS produit |
| `account.tax` (hérit.) | Application automatique de la taxe AIRSI |

**Contrôleurs JSON** :

| Route | Description |
|---|---|
| `/pos_promo/check_3x4` | Vérification de la promotion 3×4 (3 achetés = 4 livrés) |
| `/pos/active_currencies` | Liste des devises actives avec taux de change |
| `/pos/convert_currency` | Conversion devise étrangère → devise société |

**Groupes de sécurité** :

| Groupe | Rôle |
|---|---|
| `caissiere` | Caissière — accès limité à la saisie |
| `superviseur` | Superviseur — supervision et corrections |
| `assistant_magasin` | Assistant magasin — ventes + stocks |
| `responsable_magasin` | Responsable magasin — accès étendu |
| `commercial` | Commercial — ventes et comptes |

**Fonctionnalités notables** :
- Raccourci `Alt+C` pour l'ouverture manuelle du tiroir-caisse
- Popup de conversion multi-devises en temps réel
- Application automatique de la taxe AIRSI selon client et produit
- Personnalisation de la navbar (restrictions par rôle caissière/DSI)
- Import de points de fidélité via assistant (wizard)

---

### 4.2 `custom_sales` — Ventes et promotions

**Objectif** : Gestion des promotions, des tarifs et des remises avec calcul dynamique des prix.

**Modèles** :

| Modèle | Champs clés | Description |
|---|---|---|
| `sale.promotion` | `name`, `date_start`, `date_end`, `company_ids`, `line_ids`, `apply_in_pos` | En-tête de promotion |
| `sale.promotion.line` | `product_id`, `discount`, `promo_ht`, `promo_ttc`, `promo_pa`, `coeff`, `promo_tx_marque` | Règle de remise par produit |
| `product.pricelist` (hérit.) | — | Extension liste de prix |
| `product.template` (hérit.) | — | Prix de vente calculés |
| `sale.order` (hérit.) | — | Application automatique des promos |
| `res.partner` (hérit.) | — | Lien client → liste de prix |

**Logique de calcul des prix promotionnels** (3 modes) :

```
Mode 1 — Remise %    : saisie discount → calcul auto promo_ht
Mode 2 — Prix HT     : saisie promo_ht → calcul auto discount et promo_ttc
Mode 3 — Prix TTC    : saisie promo_ttc → calcul auto promo_ht et discount
```

Chaque mode utilise des champs inverses (`_inverse_*`) pour assurer la cohérence en temps réel.

**Assets POS** : `global_discount_patch.js`, `promotion_pos_patch.js`

---

### 4.3 `custom_stock` — Gestion des stocks

**Objectif** : Inventaires physiques, transferts inter-sociétés, gestion AVCO, retours et reporting.

**Modèles principaux** :

| Modèle | Description |
|---|---|
| `physical.inventory` | En-tête d'inventaire physique (états : draft → in_progress → done) |
| `physical.inventory.line` | Lignes de comptage avec quantité physique |
| `physical.inventory.retour` | Suivi des retours d'inventaire |
| `code.inventory` / `code.category.inventory` | Système de codification des inventaires |
| `team.inventory` | Équipes d'inventaire |
| `family.inventory` / `radius.inventory` | Familles produit et rayons entrepôt |
| `picking.inter.company` | Bons de transfert inter-sociétés |
| `picking.request.company` | Demandes de transfert inter-sociétés |
| `stock.picking` (hérit.) | Gestion étendue des bons de livraison/réception |
| `stock.scrap.breakers` | Suivi des casses et pertes |
| `stock.product.multicompany.view` | Vue stock multi-société |
| `stock.avco.report` | Rapport AVCO (coût moyen pondéré) |
| `avco.guard` | Garde-fou AVCO : limite les écarts à ±10 M FCFA |
| `company.state` | Statut des sociétés |

**Assistants (wizards)** :
- `product_select_wizard` — Sélection de produits
- `stock_excel_import_wizard` — Import Excel de stocks
- `reception_directe_wizard` — Réception directe fournisseur
- `retour_carton_wizard`, `retour_inventaire_wizard`, `retour_fournisseur_wizard` — Retours
- `reception_correction_info_wizard` — Correction de réceptions
- `rapport_retours_receptions_wizard` — Rapport retours/réceptions

**Workflow inventaire physique** :

```
Création inventaire (draft)
       ↓ action_start
   En cours (in_progress)
       ↓ Saisie des quantités physiques
   action_done
       ↓ Application stock.quant._apply_inventory
   Création des mouvements d'ajustement
       ↓ avco.guard vérifie : écart < ±10 M FCFA
   Validation définitive
```

---

### 4.4 `custom_loyalty` — Programme de fidélité

**Objectif** : Système de fidélité multi-famille avec accumulation de points en caisse.

**Modèles** :

| Modèle | Champs clés | Description |
|---|---|---|
| `loyalty.family` | `name`, `points_earned`, `price_threshold`, `product_category_ids` | Famille de fidélité (barème) |
| `loyalty.card` (hérit.) | — | Extension de la carte de fidélité |
| `pos.order` (hérit.) | — | Calcul des points à la commande POS |
| `pos.payment` (hérit.) | — | Paiement par points |
| `pos.payment.method` (hérit.) | — | Méthode de paiement fidélité |
| `pos.session` (hérit.) | — | Session fidélité |
| `res.partner` (hérit.) | — | Solde de points client |

**Logique d'attribution** :

```
Montant achat → Correspondance loyalty.family (price_threshold)
                       ↓
         Attribution points_earned par palier
                       ↓
         Mise à jour loyalty.card du client
```

**Données de référence** : `loyalty_family_data.xml` — familles prédéfinies (ex. : 1 point / 200 FCFA).

**Wizard** : Import en masse de cartes de fidélité via Excel.

---

### 4.5 `custom_food_credit` — Crédit alimentaire

**Objectif** : Gestion des avantages en nature (tickets restaurant / crédit alimentaire) des employés.

**Modèles** :

| Modèle | Champs clés | Description |
|---|---|---|
| `food.credit` | `name`, `partner_company_id`, `start`, `end`, `amount`, `state`, `line_ids` | Enveloppe mensuelle par société |
| `food.credit.line` | `partner_id`, `amount`, `solde`, `amount_used`, `move_ids` | Ligne par employé |
| `limit.credit` | — | Plafond de crédit par employé |
| `account.journal` (hérit.) | — | Journal dédié crédit alimentaire |
| `account.payment` (hérit.) | — | Paiement crédit alimentaire |
| `pos.payment` (hérit.) | — | Paiement POS par crédit alimentaire |

**Workflow mensuel** :

```
Wizard generate_credit_food
       ↓ Pour chaque société avec amount_food > 0
   Création food.credit (draft)
       ↓ Génération food.credit.line par employé (partenaire enfant)
   État in_progress
       ↓ Consommation en caisse POS ou facturation
   Suivi : solde = amount - amount_used
       ↓ Wizard generate_invoice_credit_food
   Génération des factures comptables
```

**Assets POS** : `paymentScreenCreditFood.js`, `partner_line_food_credit.xml`, `receipt_food_credit.xml`

---

### 4.6 `custom_api_sage_x3` — Intégration SAGE X3

**Objectif** : Synchronisation bidirectionnelle entre Odoo 19 et l'ERP SAGE X3 (commandes d'achat, livraisons, comptabilité).

**Modèles** :

| Modèle | Type | Description |
|---|---|---|
| `sage.x3.import.log` | Transient | Journal d'import (requêtes, réponses, erreurs) |
| `sage.x3.log.search.wizard` | Transient | Recherche dans les logs |
| `sage.x3.mixin` | Abstract | Authentification et helpers API |
| `purchase.order` (hérit.) | Permanent | Champs SAGE X3 sur les bons de commande |
| `account.move` (hérit.) | Permanent | Écritures comptables SAGE X3 |

**Champs ajoutés à `purchase.order`** :

| Champ | Type | Description |
|---|---|---|
| `sage_x3_submitted` | Boolean | Envoyé à SAGE X3 |
| `sage_x3_validated` | Boolean | Validé dans SAGE X3 |
| `sage_x3_delivery_received` | Boolean | Livraison reçue depuis SAGE X3 |
| `sage_x3_submitted_date` | Datetime | Date d'envoi |
| `sage_x3_delivery_date` | Datetime | Date de livraison |
| `sage_x3_response_message` | Text | Message retour SAGE X3 |
| `sage_x3_error` | Text | Message d'erreur |
| `type_command` | Selection | Type de commande |
| `type_supplier` | Selection | Type fournisseur |

**Workflow d'intégration** :

```
Bon de commande Odoo
       ↓ Validation
_submit_to_sage_x3() → POST /api/Orders/batch
       ↓ Confirmation SAGE X3
sage_x3_validated = True → button_confirm() Odoo
       ↓ CRON ou déclenchement manuel
_job_import_deliveries()
       ↓ GET /api/Orders/deliveries (filtrées par société)
_preload_data() → cache commandes + produits (anti-N+1)
       ↓ Traitement par lot de 100, commits intermédiaires
Mise à jour lignes BC (prix + qté) + stock.picking
       ↓
sage_x3_delivery_received = True
```

**Authentification** : Token Bearer avec TTL 1 heure, caché en mémoire via `_authenticate_sage_x3()`.

**Endpoints utilisés** :

| Méthode | Endpoint | Usage |
|---|---|---|
| POST | `/api/Auth/login` | Obtention du token |
| POST | `/api/Orders/batch` | Envoi de commandes |
| GET | `/api/Orders/deliveries` | Récupération livraisons |
| POST | `/api/AccountingEntries/batch` | Écritures comptables |
| GET/POST | `/api/Customers` | Synchronisation clients |
| GET/POST | `/api/Items` | Synchronisation produits |

---

### 4.7 `custom_purchase` — Achats

**Objectif** : Personnalisation des achats avec filtres produits, import de prix et réapprovisionnement.

**Modèles héritant** : `purchase.order`, `purchase.order.line`, `stock.warehouse.orderpoint`

**Fonctionnalités** :
- Filtrage des produits par statut X3 et statut entrepôt
- Assistant d'import des prix fournisseurs (Excel)
- Assistant de sélection du fournisseur de réapprovisionnement
- Gestion des points de commande (stock mini/maxi)

---

### 4.8 `custom_account` — Comptabilité

**Objectif** : Suivi budgétaire analytique et extensions comptables.

**Modèles** :

| Modèle | Description |
|---|---|
| `account.move` (hérit.) | Extensions factures/avoirs |
| `account.budget` (hérit.) | Budget standard étendu |
| `budget.analytic` | Budget analytique par axe |
| `budget.analytic.daily` | Ventilation journalière du budget analytique |

**Règles de sécurité** : Accès au budget analytique restreint par groupe.

---

### 4.9 `custom_partner` — Partenaires

**Objectif** : Extension du modèle partenaire pour les besoins SANGEL.

**Modèles héritant** : `res.partner`, `loyalty.card`, `pos.order`, `sale.order`

---

### 4.10 `custom_reports` — Rapports PDF

**Objectif** : Génération de rapports PDF métier via des assistants de filtrage.

**Assistants disponibles** (20+) :

| Assistant | Rapport |
|---|---|
| `stock_valorise_report_wizard` | Valorisation du stock |
| `sale_stat_report_wizard` | Statistiques de ventes |
| `reception_fournisseur_wizard` | Réceptions fournisseurs |
| `supplier_return_report_wizard` | Retours fournisseurs |
| `cumul_inventary_report_wizard` | Cumul inventaire |
| `stock_adjustment_report_wizard` | Ajustements de stock |
| `stock_casse_report_wizard` | Casses et pertes |
| `report_daily_sales_wizard` | Ventes journalières |
| `cadencier_sale` | Cadencier des ventes |
| `catalog_product_report_wizard` | Catalogue produits |
| `retours_consolides_report_wizard` | Retours consolidés |
| `recap_caisses_wizard` | Récapitulatif caisses |
| `livraison_report_wizard` | Bons de livraison |
| `stock_product_report_wizard` | État des stocks produits |

---

### 4.11 `custom_reliquat_report` — Rapport de reliquats

**Objectif** : Suivi du taux de satisfaction des commandes fournisseurs (qté commandée vs. reçue).

**Modèles** :

| Modèle | Champs clés | Description |
|---|---|---|
| `reliquat.report` | `date_from`, `date_to`, `period_type`, `state`, `satisfaction_rate` | En-tête rapport |
| `reliquat.report.line` | `total_qty_ordered`, `total_qty_received`, `total_qty_pending` | Ligne par référence |
| `purchase.order` (hérit.) | — | Champ de suivi reliquat |

**Périodicités supportées** : journalier, hebdomadaire, mensuel, trimestriel, bihebdomadaire, semestriel, annuel.

**Indicateur clé** : `satisfaction_rate = total_qty_received / total_qty_ordered × 100`

---

### 4.12 `custom_multi_barcode_for_products` — Multi-codes-barres

**Objectif** : Gérer plusieurs codes-barres par produit (référence principale + variantes + codes secondaires).

**Modèles** :

| Modèle | Champs clés | Description |
|---|---|---|
| `product.multiple.barcodes` | `product_multi_barcode` (unique), `product_id`, `is_active_barcode` | Code-barres alternatif |
| `product.product` (hérit.) | — | Synchronisation du code-barres actif |
| `product.template` (hérit.) | — | Gestion des codes-barres depuis le gabarit |
| `product.label.layout` (hérit.) | — | Impression d'étiquettes multi-codes |

**Contrainte** : Unicité du code-barres dans toute la base (`@api.constrains`).

**Asset POS** : `pos_multi_barcode.js` — reconnaissance multi-codes-barres en caisse.

**Wizard** : Import en masse de codes-barres via Excel.

---

### 4.13 `custom_price_change_tracker` — Suivi des prix

**Objectif** : Historisation de toutes les modifications de prix produits avec alertes quotidiennes.

**Modèles** :

| Modèle | Description |
|---|---|
| `product.price.history` | Historique des prix (date, ancien prix, nouveau prix, utilisateur) |
| `product.template` (hérit.) | Déclenchement de l'enregistrement à chaque modification de prix |

**Assistants** : `product_price_history_wizard`, `product_price_analysis_wizard`

**Cron** : Notification quotidienne des changements de prix (`ir_cron_data.xml`).

**Bonus** : Génération d'étiquettes codes-barres depuis l'historique.

---

### 4.14 `cfao_dashboard_report` — Tableau de bord CFAO

**Objectif** : Dashboard multi-société avec comparaison N/N-1 et analyse budgétaire.

**Modèle** : `report.cfao.dashboard`

**4 périodes d'analyse** : Jour / Semaine / Mois / Année

**Indicateurs** :
- Chiffre d'affaires (commandes de vente + commandes POS)
- Marges brutes
- Débits (engagements)
- Stocks par département
- Comparaison N-1
- Analyse budgétaire

**Filtres** : par département (catégorie de produit), par société

---

### 4.15 `dashboard_management_administration` — Dashboard Admin

**Objectif** : Tableau de bord administratif avec graphiques interactifs (Chart.js).

**Modèles** :

| Modèle | Description |
|---|---|
| `managment.admin` | Paramètres du dashboard |
| `dashboard.data` | Données consolidées |
| `pos.actions.dashboard` | Actions POS en temps réel |

**Contrôleur** : `ManagmentAdminController` — endpoints JSON pour les données graphiques.

**Assets** : Bibliothèque Chart.js, CSS/JS personnalisés pour les dashboards ventes, POS, achats.

**Analyse Top 5 clients** avec filtrage par date.

---

### 4.16 `fne_certification` — Certification FNE

**Objectif** : Certification des factures sur la plateforme FNE (administration fiscale).

**Modèles** :

| Modèle | Description |
|---|---|
| `account.move` (hérit.) | Champs FNE (numéro certification, statut) |
| `account.tax` (hérit.) | Configuration TVA FNE |
| `fne.config.setting` | Paramètres de connexion FNE |
| `res.partner` (hérit.) | Données de certification partenaire |

**Assistants** : `fne_certification_wizard` (certification), `fne_certification_refund` (avoirs)

**Rapport** : `report_invoice_fne` — facture au format FNE.

---

### 4.17 `stock_avco_correction` — Correction AVCO

**Objectif** : Correction des coûts moyens pondérés (AVCO) suite à la migration depuis ProgMag.

**Fonctionnalités** :
- Import Excel de corrections AVCO
- Règle de tolérance à 5 % (prix conservé si écart acceptable)
- Sauvegarde du prix d'origine pour la traçabilité
- Isolation multi-société

**Assistants** :
- `stock_avco_import_wizard` — Import des corrections
- `sale_margin_recompute_wizard` — Recalcul des marges
- `product_status_import_wizard` — Import du statut produits

---

### 4.18 `pos_history_import` — Import historique POS

**Objectif** : Injection en masse d'un historique de ventes POS depuis Excel (migration de données).

**Modèles** :

| Modèle | Description |
|---|---|
| `pos.import.wizard` | Assistant principal d'import |
| `pos.import.preview.line` | Lignes de prévisualisation avant import |

**Processus** :
1. Téléchargement du gabarit Excel
2. Remplissage (référence produit, client, montant, paiement, date)
3. Chargement et prévisualisation
4. Import → création automatique de `pos.session`, `pos.order`, `pos.order.line`, `pos.payment`
5. Journal d'erreurs détaillé

**Regroupement** : par jour ou par mois.

**Dépendance Python** : `openpyxl`

---

### 4.19 `hide_menu_user` — Masquage de menus

**Objectif** : Contrôle de la visibilité des menus par utilisateur (indépendant des groupes).

**Modèles héritant** : `res.users`, `ir.ui.menu`

---

### 4.20 `queue_job` — File de travaux asynchrones

**Objectif** : Exécution asynchrone de traitements lourds (module OCA communautaire).

**Modèles** :

| Modèle | Description |
|---|---|
| `queue.job` | Travaux en attente / en cours / terminés |
| `queue.job.channel` | Canaux de priorité |
| `queue.job.function` | Registre des fonctions de travaux |
| `queue.job.lock` | Verrous anti-doublon |

**Utilisé par** : `custom_api_sage_x3` pour l'import asynchrone des livraisons SAGE X3.

---

## 5. Modèles de données clés

### Schéma `food.credit`

```
food.credit
├── name            : Char (auto-séquence)
├── partner_company_id : Many2one(res.partner)
├── start / end     : Datetime
├── amount          : Float (enveloppe mensuelle)
├── total_amount_limit : Float (computed)
├── amount_used     : Float (computed, somme lignes)
├── invoiced        : Boolean
├── move_id         : Many2one(account.move)
├── state           : Selection [draft, in_progress, close, done]
└── line_ids        : One2many(food.credit.line)

food.credit.line
├── partner_id      : Many2one(res.partner) ← employé
├── amount          : Float
├── start / end     : Datetime
├── food_id         : Many2one(food.credit)
├── solde           : Float (computed = amount - amount_used)
├── amount_used     : Float
└── move_ids        : Many2many(account.move)
```

### Schéma `sale.promotion`

```
sale.promotion
├── name            : Char (code promo)
├── company_ids     : Many2many(res.company)
├── date_start / date_end : Date
├── line_ids        : One2many(sale.promotion.line)
├── apply_in_pos    : Boolean
└── active          : Boolean

sale.promotion.line
├── promotion_id    : Many2one(sale.promotion)
├── product_id      : Many2one(product.template)
├── discount        : Float [0-100]
├── promo_ht        : Float
├── promo_ttc       : Float (inverse)
├── promo_pa        : Float (coût promo)
├── price_ht / price_ttc : Float (computed depuis produit)
├── coeff           : Float (coefficient)
├── promo_coeff     : Float
├── promo_tx_marque : Float (taux de marque)
├── qty_available   : Float (computed, stock réel)
└── virtual_available : Float (computed, stock prévisionnel)
```

### Schéma `physical.inventory`

```
physical.inventory
├── name            : Char
├── code_inventory_id : Many2many(code.inventory)
├── code_category_id : Many2one(code.category.inventory)
├── team_inventory_id : Many2one(team.inventory)
├── inventory_mode  : Selection [normal, libre]
├── state           : Selection [draft, in_progress, done]
├── line_quant_ids  : One2many(stock.quant)
├── physical_line_ids : One2many(physical.inventory.line)
├── company_id      : Many2one(res.company)
├── date            : Datetime
├── date_done       : Datetime
├── is_negative_stock : Boolean
└── note            : Text
```

### Schéma `purchase.order` (champs SAGE X3)

```
purchase.order (hérit.)
├── sage_x3_submitted       : Boolean
├── sage_x3_validated       : Boolean
├── sage_x3_delivery_received : Boolean
├── sage_x3_submitted_date  : Datetime
├── sage_x3_delivery_date   : Datetime
├── sage_x3_response_message : Text
├── sage_x3_error           : Text
├── type_command            : Selection
└── type_supplier           : Selection
```

---

## 6. Workflows métier

### 6.1 Commande d'achat → SAGE X3 → Livraison

```
1. Création du bon de commande Odoo
2. Validation → _submit_to_sage_x3() → POST /api/Orders/batch
3. Réception de la confirmation SAGE X3
   → sage_x3_validated = True
   → button_confirm() → BC confirmé dans Odoo
4. CRON ou déclenchement manuel : _job_import_deliveries()
   → GET /api/Orders/deliveries (par société, depuis last_import_date)
   → _preload_data() (cache anti-N+1)
   → Traitement par lots de 100 avec commits intermédiaires
   → Mise à jour lignes BC (prix + qté) + création stock.picking
   → sage_x3_delivery_received = True
```

### 6.2 Session POS et clôture

```
1. Ouverture de session POS (caissière/superviseur)
2. Vente : scan multi-codes-barres → recherche produit
   → Application auto promo (si apply_in_pos = True)
   → Application auto taxe AIRSI (selon client + produit)
3. Paiement : espèces / carte / crédit alimentaire / fidélité
   → Conversion multi-devises si paiement en devise étrangère
4. Clôture :
   → rapport_validation (rapport des validations)
   → cloture_caisse (rapport de caisse)
   → Réconciliation des paiements
```

### 6.3 Génération du crédit alimentaire mensuel

```
1. Wizard generate_credit_food
2. Pour chaque société avec amount_food > 0 :
   → Création food.credit (draft)
   → Génération food.credit.line par employé (partenaire enfant)
3. Passage en état in_progress
4. Consommation en caisse POS → déduction du solde
5. Wizard generate_invoice_credit_food
   → Génération des factures comptables par enveloppe
6. État done après facturation complète
```

### 6.4 Inventaire physique

```
1. Création de l'inventaire (draft)
   → Affectation : équipe, codes, catégorie
2. action_start → in_progress
3. Saisie des quantités physiques par ligne
4. action_done :
   → _apply_inventory() sur stock.quant
   → Création des mouvements d'ajustement
   → avco.guard : vérification écart AVCO < ±10 M FCFA
5. Validation définitive
```

---

## 7. Sécurité et droits d'accès

### Groupes personnalisés (custom_pos)

| Groupe | Lecture | Écriture | Suppression | Périmètre |
|---|---|---|---|---|
| `caissiere` | POS orders, sessions | POS orders limité | — | Caisse uniquement |
| `superviseur` | POS, stock, comptes | POS, stock, comptes | POS, stock | Supervision point de vente |
| `assistant_magasin` | Ventes, achats, stock, POS | Ventes, achats, stock, POS | Ventes, achats, stock | Entrepôt et vente |
| `responsable_magasin` | Tout | Tout | Tout | Gestion complète magasin |
| `commercial` | Ventes, comptes (limité) | Ventes, comptes (limité) | Ventes | Commercial terrain |

### Règles de données (Record Rules)
- Stocks et inventaires : isolation par société (`company_id`)
- Transferts inter-sociétés : restriction aux sociétés autorisées
- Sécurité produits : visibilité selon le statut produit

---

## 8. APIs et intégrations externes

### SAGE X3 REST API

**URL de base** : `http://172.16.2.150:8030` (configurable via paramètre système)

**Authentification** : Bearer token (TTL 1h, caché en mémoire)

**Format des commandes** :

```json
{
  "commandes": [{
    "siteVente": "VRIDI",
    "DateCommande": "2026-05-22T10:00:00",
    "Client": "YOP01",
    "Devise": "XOF",
    "Magasin": "PRINCIPAL",
    "ReferenceCommandeClient": "PO123456",
    "items": [{
      "ligne": 1000,
      "article": "PROD001",
      "TexteLigne": "Libellé produit",
      "quantite": 10
    }]
  }]
}
```

### FNE (Certification fiscale)
- Workflow de certification des factures et avoirs
- Configuration de la taxe TVA FNE
- Numéro de certification stocké sur `account.move`

### POS Controllers internes

| Route | Méthode | Description |
|---|---|---|
| `/pos_promo/check_3x4` | POST | Vérifie la règle promotionnelle 3×4 |
| `/pos/active_currencies` | GET | Retourne devises actives + taux |
| `/pos/convert_currency` | POST | Convertit un montant en devise locale |

---

## 9. Personnalisations du POS (JavaScript)

### Patches JavaScript (OWL / Odoo 17+)

| Fichier | Rôle |
|---|---|
| `payment_screen_patch.js` | Personnalisation de l'écran de paiement |
| `currency_payment_screen_patch.js` | Popup de conversion multi-devises |
| `closing_popup_patch.js` | Popup de clôture de session |
| `money_details_popup_patch.js` | Détail du fond de caisse |
| `airsi_patch.js` | Application automatique de la taxe AIRSI |
| `promotion_pos_patch.js` | Application des promotions de vente |
| `OrderlineCustom.js` | Personnalisation des lignes de commande |
| `ProductScreen.js` | Écran de sélection produit |
| `loyalty_single_line.js` | Affichage des points fidélité |
| `pos_navbar_patch.js` | Barre de navigation (restrictions par rôle) |
| `cashbox_button.js` | Ouverture manuelle du tiroir (Alt+C) |
| `logout_button.js` | Bouton de déconnexion utilisateur |
| `price_ttc_patch.js` | Affichage du prix TTC |
| `ticket_screen_refund_patch.js` | Gestion des remboursements |
| `pos_multi_barcode.js` | Reconnaissance multi-codes-barres |
| `paymentScreenCreditFood.js` | Paiement par crédit alimentaire |
| `global_discount_patch.js` | Remise globale POS |

### Templates XML POS

| Fichier | Rôle |
|---|---|
| `currency_conversion_popup.xml` | Popup de conversion de devise |
| `cash_move_hide_cash_in.xml` | Masquage de l'entrée de caisse |
| `custom_receipt_header.xml` | En-tête personnalisé des tickets |
| `orderline_customization.xml` | Ligne de commande enrichie |
| `pos_receipt_custom.xml` | Ticket de caisse personnalisé |
| `pos_navbar_caissiere_patch.xml` | Navbar restreinte caissière |
| `partner_line_food_credit.xml` | Ligne client avec crédit alimentaire |
| `receipt_food_credit.xml` | Ticket avec crédit alimentaire |

---

## 10. Rapports et tableaux de bord

### Rapports PDF (Qweb)

| Catégorie | Rapports |
|---|---|
| **Stock** | Valorisation, ajustements, casses, état produits |
| **Ventes** | Journalier, statistiques, cadencier |
| **Achats** | Réceptions fournisseurs, retours fournisseurs |
| **Inventaire** | Inventaire physique, décompte, bon réception |
| **Caisse** | Récapitulatif caisses, retours/réceptions |
| **Reliquat** | Taux de satisfaction commandes |
| **Catalogue** | Export catalogue produits |
| **FNE** | Facture au format certification FNE |
| **Crédit alimentaire** | Plafonds, factures crédit |

### Tableaux de bord

| Dashboard | Indicateurs |
|---|---|
| **CFAO Dashboard** | CA, marges, débits, stocks par société/département (J/S/M/A + N-1) |
| **Management Admin** | KPIs ventes, achats, POS avec graphiques Chart.js, Top 5 clients |
| **POS Actions** | Actions POS en temps réel, métriques session |

---

## 11. Tâches planifiées (Crons)

| Cron | Module | Fréquence | Action |
|---|---|---|---|
| AVCO Guard | `custom_stock` | Quotidien | Vérifie les écarts AVCO > ±10 M FCFA |
| Price Change Notif. | `custom_price_change_tracker` | Quotidien | Notification des modifications de prix |
| Reliquat Report | `custom_reliquat_report` | Configurable | Génération automatique des rapports |
| SAGE X3 Import | `custom_api_sage_x3` | Planifié | Import des livraisons depuis SAGE X3 |
| Food Credit Generate | `custom_food_credit` | Mensuel | Génération des crédits alimentaires |

---

## 12. Dépendances externes Python

| Bibliothèque | Usage |
|---|---|
| `openpyxl` | Lecture/écriture Excel (imports, exports) |
| `requests` | Appels HTTP vers SAGE X3 |
| `python-dateutil` | Calculs de dates (relativedelta pour mensuel) |

Installation :
```bash
pip install openpyxl requests python-dateutil
```

---

## 13. Paramètres système

Les paramètres suivants doivent être configurés via **Paramètres → Technique → Paramètres système** :

| Clé | Valeur par défaut | Description |
|---|---|---|
| `sage_x3.base_url` | `http://172.16.2.150:8030` | URL de base de l'API SAGE X3 |
| `sage_x3.username` | `odoo` | Identifiant SAGE X3 |
| `sage_x3.password` | `InterfaceX3_Odoo` | Mot de passe SAGE X3 |
| `sage_x3.last_import_date.company_{id}` | ISO timestamp | Date du dernier import par société |

> **Important** : Le mot de passe SAGE X3 est stocké en clair dans les paramètres système. Il est recommandé de le stocker dans un coffre-fort de secrets en production.

---

*Documentation générée le 22 mai 2026 — Projet SANGEL, Odoo 19*
