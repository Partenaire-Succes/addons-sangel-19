# custom_account — Personnalisation de la comptabilité (Odoo 19)

Ce module ajoute un **suivi de budget analytique journalier** et un lien automatique avec les budgets analytiques d’Odoo (`account_budget`).

## Fonctionnalités principales

### 1) Budget journalier par compte analytique

Nouveaux modèles :

- `daily.budget.analytic` : *Budget journalier* (en-tête)
- `daily.budget.analytic.line` : *Lignes journalières* (une ligne par jour)

Objectif : définir un budget **jour par jour** sur une période, puis comparer le **réalisé** (écritures comptables postées) au budget.

### 2) Recalcul automatique du réalisé

Quand des écritures comptables changent, le module déclenche un recalcul du **Montant Réel** sur les lignes de budget journalier concernées.

Sont pris en compte :

- les `account.move.line` en état posté (`parent_state = posted`)
- avec un compte analytique présent via la distribution analytique (`distribution_analytic_account_ids`)
- dans la période (date) de la ligne journalier.

### 3) Lien avec les budgets analytiques (`account_budget`)

Lors de la validation d’un budget journalier, le module crée aussi un enregistrement `budget.analytic` (Odoo Budget) lié au budget journalier.

## Où trouver le menu

Après installation, un menu apparaît sous **Comptabilité** :

- **Comptabilité → Écritures → Budget Journalier**

(techniquement : menu `menu_daily_budget_analytic` parent `account.menu_finance_entries`).

## Processus utilisateur (pas à pas)

### A) Créer un budget journalier

1. Ouvrir **Budget Journalier**
2. Cliquer **Créer**
3. Renseigner :
   - **Nom du budget**
   - **Type de budget** (Revenu / Note de frais / Les deux)
   - **Plan Analytique**
   - **Compte Analytique** (filtré sur le plan)
   - **Période** (Date de début / Date de fin)
4. Enregistrer.

### B) Générer les lignes journalières

- En état **Brouillon**, cliquer **Générer les lignes journalières**.

Effet :

- création d’une ligne par jour dans l’onglet *Les lignes de budget journalière*
- passage à l’état **En attente**.

### C) Saisir les montants budgetés par jour

Dans l’onglet *Les lignes de budget journalière* :

- saisir **Budget Mensuel** (champ `budget_amount`) pour chaque journée.

Remarque : dans l’implémentation actuelle, les lignes générées sont créées **sans montant** ; c’est l’utilisateur qui renseigne les montants.

### D) Valider le budget

- En état **En attente**, cliquer **Valider**.

Contrôles effectués :

- il doit exister des lignes
- chaque ligne doit avoir un budget strictement **> 0**.

Effet :

- création d’un budget Odoo `budget.analytic` lié
- passage à l’état **En cours**
- les colonnes **Montant Réel**, **Réalisé (%)** et **Écart** deviennent visibles.

### E) Suivre le réalisé et l’écart

En **En cours**, les lignes affichent :

- **Montant Réel** : calculé depuis les écritures postées
- **Écart** : Budget − Réel
- **Réalisé (%)** : Réel / Budget

Le réalisé est recalculé automatiquement lorsque des écritures liées au compte analytique changent.

### F) Clôturer

- En état **En cours**, cliquer **Clôturer**.

Effet :

- passage à l’état **Terminé**
- clôture du budget `budget.analytic` lié.

## Droits d’accès

Le module déclare des accès (sans restriction de groupe) :

- `daily.budget.analytic`
- `daily.budget.analytic.line`

Fichier : `security/ir.model.access.csv`.

Si vous souhaitez limiter à un groupe (ex : comptables), il faudra définir un `group_id` sur les lignes d’accès.

## Notes & limitations (important)

- **Calcul du réalisé** : le champ `actual_amount` somme actuellement uniquement les **crédits** (`credit`).
  - Pour certains cas (dépenses), un calcul `debit`, ou `balance`, ou une logique selon `budget_type` peut être nécessaire.
- **Analytique** : le module s’appuie sur la **distribution analytique** (`distribution_analytic_account_ids`). Assurez-vous que vos écritures utilisent bien cette mécanique.
- **Performance** : sur une grosse volumétrie d’écritures, recalculer à chaque création/modification peut être coûteux. Le module restreint le recalcul aux budgets et dates impactés.

## Références techniques (pour développeurs)

- Modèles : `models/budget_analytic_daily.py`, `models/budget_analytic.py`, `models/account_move.py`
- Vues :
  - `views/budget_analytic_daily_view.xml` (form/list + menu)
  - `views/account_budget_inherit_views.xml` (extension budget Odoo)
