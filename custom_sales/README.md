# Module `custom_sales` — Guide utilisateur (Odoo)

Ce module ajoute des fonctionnalités avancées pour la gestion des ventes, des listes de prix, des produits multi-sociétés et des remises automatiques dans Odoo.

> **Public visé** : utilisateurs métier (commerciaux, responsables ventes, gestionnaires de produits, administrateurs de prix).
> **Objectif** : vous guider sur **où cliquer**, **comment utiliser les écrans**, et **quoi vérifier** pour exploiter au mieux les personnalisations apportées.

---

## 1) Accès rapides (où cliquer)

### A. Listes de prix multi-sociétés

- **Ventes → Produits → Listes de prix**
- Ouvrir une liste de prix : champ **Sociétés** ("Sociétés autorisées") pour limiter la visibilité par société
- Bouton **Ajouter produits (multiple)** pour ajouter plusieurs produits ou catégories à la liste de prix via un assistant

### B. Assistant d’ajout de produits à une liste de prix

- Depuis une liste de prix, cliquer sur **Ajouter produits (multiple)**
- L’assistant "Sélectionner des Produits" permet de :
  - Choisir d’appliquer la règle à des **produits** ou à des **catégories**
  - Sélectionner les produits ou catégories concernés
  - Définir le **prix fixe**, la **quantité minimale**, et la période de validité
  - Valider pour créer les lignes de prix correspondantes

### C. Produits multi-sociétés

- **Ventes → Produits** ou **Inventaire → Produits**
- Dans la fiche produit : champ **Sociétés** ("Sociétés autorisées") pour restreindre la visibilité

### D. Factures clients (accès rapide)

- **Ventes → Factures** (menu ajouté)
- Affiche directement la liste des factures clients

---

## 2) Fonctionnalités principales

### 2.1 Visibilité multi-sociétés

- Les produits, variantes et listes de prix comportent un champ **Sociétés**
- Si votre société n’est pas sélectionnée, vous ne verrez pas l’élément dans les listes
- Pour toute absence, demandez à votre administrateur d’ajouter votre société à l’enregistrement

### 2.2 Remises automatiques sur les lignes de vente

- Lors de l’ajout d’un produit à un devis/commande, une remise peut s’appliquer automatiquement si :
  - Le client est éligible à une remise (paramétré dans sa fiche)
  - Le produit autorise la remise sur ligne
  - Les dates de validité sont respectées
- Si la remise attendue n’apparaît pas, vérifiez les paramètres du client ou contactez l’administrateur

### 2.3 Assistant d’ajout de produits à une liste de prix

- Permet d’ajouter en masse des produits ou catégories à une liste de prix
- Saisie du prix, quantité minimale, période de validité
- Gain de temps pour la gestion des promotions ou tarifs spécifiques

---

## 3) Étapes d’utilisation courantes

### Ajouter plusieurs produits à une liste de prix

1. Ouvrir **Ventes → Produits → Listes de prix**
2. Sélectionner la liste de prix à modifier
3. Cliquer sur **Ajouter produits (multiple)**
4. Choisir d’appliquer à des **produits** ou **catégories**
5. Sélectionner les éléments, renseigner le prix, la quantité minimale, les dates
6. Valider pour créer les règles

### Vérifier la visibilité d’un produit ou d’une liste de prix

- Si un produit ou une liste de prix n’apparaît pas, vérifier le champ **Sociétés**
- Demander à l’administrateur d’ajouter votre société si besoin

### Accéder rapidement aux factures clients

- Menu **Ventes → Factures** pour consulter ou créer des factures clients

---

## 4) Astuces & dépannage rapide

- **Produit/liste de prix introuvable** : vérifier le champ **Sociétés**
- **Bouton assistant non visible** : droits insuffisants, contacter l’administrateur
- **Prix ou remise incorrects** : vérifier la saisie dans l’assistant et les paramètres du client

---

## 5) Checklist de test rapide

- [ ] Je peux voir et modifier le champ **Sociétés** sur un produit et une liste de prix
- [ ] J’utilise l’assistant pour ajouter plusieurs produits à une liste de prix
- [ ] Une remise s’applique automatiquement sur une ligne de vente si le client est éligible
- [ ] Je retrouve le menu **Factures** sous Ventes

---

Pour toute question ou besoin de capture d’écran, contactez votre administrateur ou l’équipe support.
