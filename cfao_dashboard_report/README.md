# CFAO Dashboard Report — Module Odoo 19

## 📋 Description
Module de rapport quotidien multi-société pour CFAO Retail.
Génère un PDF A4 paysage avec 4 périodes : **Jour / Semaine / Mois / Année (YTD)**.

---

## 🏗️ Structure du module
```
cfao_dashboard_report/
├── __manifest__.py              # Déclaration du module
├── __init__.py
├── models/
│   └── report_cfao_dashboard.py # Logique de calcul des KPIs
├── wizard/
│   ├── cfao_dashboard_wizard.py # Formulaire de sélection
│   └── cfao_dashboard_wizard_views.xml
├── report/
│   ├── cfao_dashboard_report.xml    # Action rapport + format papier
│   └── cfao_dashboard_template.xml  # Template QWeb du rapport
└── security/
    └── ir.model.access.csv
```

---

## 🚀 Installation

1. **Copier** le dossier `cfao_dashboard_report` dans votre répertoire addons Odoo :
   ```bash
   cp -r cfao_dashboard_report /opt/odoo/addons/
   ```

2. **Mettre à jour la liste des modules** dans Odoo :
   Paramètres → Activer le mode développeur → Mise à jour de la liste des applications

3. **Installer** le module "CFAO - Tableau de Bord Quotidien"

4. **Redémarrer** Odoo si nécessaire :
   ```bash
   sudo systemctl restart odoo
   ```

---

## 📊 Utilisation

1. Aller dans le menu **CFAO Retail → Rapports → Tableau de Bord Quotidien**
2. Sélectionner la **date d'analyse**
3. Sélectionner la ou les **société(s)**
4. Cliquer sur **Imprimer le Rapport PDF**

---

## 🔧 Configuration recommandée

### Hiérarchie des catégories produit
Le rapport s'appuie sur la hiérarchie des catégories :
```
All
└── Département 01 PGC       ← Niveau Département
    ├── Rayon 10 - Boissons  ← Niveau Rayon
    ├── Rayon 11 - Droguerie
    ├── Rayon 14 - Epicerie
    └── ...
└── Département 02 PF
    ├── Rayon 15 - Produits Frais
    └── ...
```
**À paramétrer dans** : Inventaire → Configuration → Catégories de produits

### Budget
Pour activer la colonne **Ecart/Budget**, ajouter un champ `budget_ca` sur la catégorie produit
ou utiliser le module `account_budget` d'Odoo.

### Produits importés vs locaux
Ajouter un champ booléen `is_imported` sur `product.template` :
```python
is_imported = fields.Boolean('Produit importé', default=False)
```

---

## 📐 Colonnes du rapport

| Groupe              | Colonnes                                           |
|---------------------|----------------------------------------------------|
| **CA (en millier)** | Kilo TTC, Kilo HT, %N-1, %Promo, %Imp, %Loc.     |
| **Ecart/Budgété**   | Kilo, %Bud                                         |
| **Débits**          | Kilo, %Prog                                        |
| **Marge (en mill.)** | Kilo, %, %Imp, %Loc., %hs promo, %Promo, %Dem   |
| **Panier Moyen**    | Montant, %N-1                                      |
| **Stock reçu**      | Qté (en millier), Valo PV (en millier), Couverture |

### Couleurs dans le rapport :
- 🔴 **Rouge** = valeur négative ou dégradation vs N-1
- 🟢 **Vert** = valeur positive ou progression vs N-1
- 🟣 **Violet foncé** = ligne Total Département
- ⬛ **Noir** = ligne Grand Total

---

## 🔄 Sources de données

| KPI          | Source Odoo                                   |
|--------------|-----------------------------------------------|
| CA TTC / HT  | `pos.order.line` + `sale.order.line`          |
| Marge        | CA HT − (prix de revient × quantité vendue)   |
| Débits       | Nb de `pos.order` + `sale.order` validés      |
| Panier Moyen | CA TTC ÷ Nombre de tickets                    |
| Stock reçu   | `stock.move` (type: réception)                |
| Couverture   | Stock valeur ÷ (CA HT ÷ nb jours période)     |
| N-1          | Même période, année précédente                |

---

## 🛠️ Développements futurs

- [ ] Export Excel (XLSX)
- [ ] Envoi automatique par email (planification cron)
- [ ] Gestion des budgets par rayon
- [ ] Drill-down par famille produit
- [ ] Tableau de bord web interactif (Odoo BI)

---

## 📞 Support
Module développé pour CFAO Retail — Multi-société Odoo 19
