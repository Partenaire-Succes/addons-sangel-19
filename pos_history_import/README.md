# POS History Import — Odoo 19

Module d'import des historiques de ventes POS depuis un fichier Excel.
Conçu pour la migration depuis un ancien système (ProjetMag, Lightspeed, CSV, etc.)

---

## 📦 Installation

### 1. Dépendance Python
```bash
pip install openpyxl
```

### 2. Copier le module
```bash
cp -r pos_history_import /path/to/odoo/addons/
```

### 3. Mettre à jour la liste des modules
```
Paramètres → Activer le mode développeur
Paramètres → Technique → Mettre à jour la liste des modules
Rechercher "POS Import Historique" → Installer
```

---

## 🚀 Utilisation

### Accès
```
Point de Vente → Configuration → Import Historique des Ventes
```

### Étape 1 : Télécharger le template
Cliquez sur **📥 Télécharger le template Excel** pour obtenir le fichier modèle.

### Étape 2 : Remplir le template

Le fichier contient 2 feuilles :
- **Import POS** : vos données de vente
- **📋 Instructions** : guide détaillé

#### Colonnes obligatoires (fond bleu foncé)

| Colonne | Description |
|---------|-------------|
| `date_order` | Date/heure de la commande. Format : JJ/MM/AAAA HH:MM |
| `product_ref` | Référence interne du produit dans Odoo |
| `qty` | Quantité vendue |
| `price_unit` | Prix unitaire TTC |
| `payment_method` | Nom du mode de paiement (sur la 1ère ligne de chaque commande) |
| `amount_paid` | Montant total payé (sur la 1ère ligne de chaque commande) |

#### Colonnes optionnelles (fond bleu clair)

| Colonne | Description |
|---------|-------------|
| `order_ref` | Référence de commande. Si vide, générée automatiquement. |
| `customer_ref` | Référence interne du client dans Odoo |
| `customer_name` | Nom du client (crée un nouveau contact si absent) |
| `product_name` | Nom du produit (fallback si `product_ref` non trouvé) |
| `discount` | Remise en % (ex: 10 pour 10%) |
| `note` | Note interne sur la ligne |

### Commandes multi-lignes

Pour une commande avec plusieurs produits :
```
date_order          | order_ref | product_ref | qty | price_unit | payment_method | amount_paid
15/01/2024 09:30   | CMD-001   | CAFE-001    | 2   | 1500       | Cash           | 3800
15/01/2024 09:30   | CMD-001   | CROI-001    | 1   | 800        |                |
```

### Étape 3 : Configurer l'import
- **Point de Vente** : sélectionner le POS cible
- **Regroupement** :
  - *Par Jour* → 1 session POS par jour de vente (recommandé)
  - *Par Mois* → 1 session POS par mois

### Étape 4 : Charger le fichier et lancer
Cliquez sur **🚀 Lancer l'import** et patientez.

---

## 📊 Ce qui est créé dans Odoo

| Modèle | Description |
|--------|-------------|
| `pos.session` | Une session clôturée par période (jour/mois), nommée `[IMPORT] YYYY-MM-DD` |
| `pos.order` | Une commande par `order_ref` unique, état `done` |
| `pos.order.line` | Une ligne par produit, avec calcul automatique des taxes |
| `pos.payment` | Un paiement par commande, lié au mode de paiement |
| `res.partner` | Créé automatiquement si `customer_name` fourni et non trouvé |

---

## ⚠️ Prérequis

Avant de lancer l'import, vérifiez que :

1. ✅ Les **produits** existent dans Odoo avec leur `Réf. interne`
2. ✅ Les **modes de paiement** sont configurés sur votre POS
3. ✅ Le **Point de Vente** est configuré
4. ✅ `openpyxl` est installé sur le serveur Python

---

## 🔧 Dépannage

### "Colonne obligatoire manquante"
→ Vous n'utilisez pas le template fourni. Téléchargez-le et ne modifiez pas les noms de colonnes.

### "Produit introuvable"
→ Vérifiez que la `Réf. interne` du produit dans Excel correspond exactement à celle dans Odoo.

### "openpyxl non installé"
```bash
# Sur le serveur Odoo
pip install openpyxl
# Puis redémarrer Odoo
```

### Sessions déjà existantes
Le module évite les doublons : si une session `[IMPORT] 2024-01-15` existe déjà,
elle sera réutilisée sans en créer une nouvelle.

---

## 🏗️ Structure du module

```
pos_history_import/
├── __manifest__.py          # Déclaration du module
├── __init__.py
├── models/
│   ├── __init__.py
│   └── pos_import_wizard.py # Logique principale d'import
├── views/
│   ├── pos_import_wizard_views.xml  # Formulaire wizard
│   └── pos_import_menu.xml          # Entrée de menu
├── security/
│   └── ir.model.access.csv  # Droits d'accès
└── README.md
```

---

## 📝 Licence

LGPL-3 — Odoo Community
