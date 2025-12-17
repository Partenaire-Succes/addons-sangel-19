# Guide utilisateur — Carte de fidélité (module `custom_loyalty`)

Ce guide explique **comment utiliser** la carte de fidélité dans Odoo (côté utilisateur final), et **comment tester** que tout fonctionne.

> Important : ce module s’appuie sur les fonctionnalités Odoo de fidélité + POS. Il **personnalise** surtout :
>
> - les règles d’éligibilité des produits,
> - le calcul des points (1 point / 200 F ou 1 point / 1000 F selon la catégorie),
> - l’utilisation de la carte comme **moyen de paiement** (POS / ventes / comptabilité),
> - l’écran “Rendu monnaie” (créditer la carte).

---

## 1) Pour qui ?

- **Caissier / Vendeur (POS)** : encaisser, appliquer un paiement “Carte de fidélité”, créditer la carte via “Rendu monnaie (FCFA)”.
- **Commercial (Ventes)** : confirmer une commande en payant via “Carte de fidélité”, créditer la carte via “Rendu monnaie”.
- **Comptable / Caissier back-office** : enregistrer un paiement sur facture avec un journal “Carte de fidélité”.
- **Administrateur** : paramétrage des catégories/produits, méthodes de paiement POS, etc.

---

## 2) Ce que fait la carte de fidélité (en simple)

- La **carte de fidélité** contient un **solde de points**.
- Dans ce module, les points sont utilisés comme un **crédit** (exprimé en FCFA dans les libellés).
- On peut :
  1) **Gagner** des points sur des produits éligibles (calcul automatique)
  2) **Dépenser** des points en paiement (si un moyen/journal “Carte de fidélité” est utilisé)
  3) **Créditer** la carte manuellement via “Rendu monnaie”

---

## 3) Pré-requis avant de tester

1. Les applications doivent être installées : **Point de Vente**, **Fidélité** (et modules dépendants déjà présents dans votre base).
2. Le client doit exister (Contacts).
3. Le client doit avoir une **carte de fidélité** (Odoo standard) et un solde.
4. Des produits doivent être correctement configurés (éligibles + catégorie avec règle de fidélité).

---

## 4) Paramétrage (Administrateur)

### A. Configurer les catégories (ratio de points)

Chemin recommandé : **Produits → Configuration → Catégories de produits**

Dans la catégorie, renseigner **Famille Fidélité** :

- **Pas de points de fidélité**
- **1 point / 200 F**
- **1 point / 1000 F**

✅ Résultat attendu : la règle s’applique à tous les produits de la catégorie.

### B. Configurer les produits (éligibilité)

Chemin : **Produits → Produits** (ouvrir une fiche produit)

Dans la section **Fidélité** :

- **Éligible aux points de fidélité** : coché = le produit peut générer des points
- **Famille Fidélité** : affichée depuis la catégorie (lecture seule)

✅ Résultat attendu : un produit non éligible ne génère aucun point.

### C. Marquer un client “carte de fidélité”

Chemin : **Contacts → Contacts** (ouvrir le client)

Dans l’onglet/section lié(e) au **Crédit** (page “crédit”), vous trouverez :

- **A une carte de fidélité**

Note : cette case se met automatiquement à jour selon si le client possède une carte de fidélité.

✅ Résultat attendu : si le client n’a pas de carte, certaines opérations seront bloquées.

### D. Activer un moyen de paiement POS “Carte de fidélité”

Chemin : **Point de Vente → Configuration → Moyens de paiement**

Sur un moyen de paiement, vous trouverez :

- **Carte de fidélité** (case)

✅ Résultat attendu : lorsque ce moyen est utilisé dans le POS, Odoo vérifie le solde avant d’accepter le paiement.

### E. (Optionnel) Activer un journal comptable “Carte de fidélité”

Chemin : **Comptabilité → Configuration → Journaux**

Sur un journal, vous trouverez :

- **Carte de fidélité** (case)

✅ Résultat attendu : lors de l’enregistrement d’un paiement sur facture via ce journal, Odoo contrôle le solde et déduit les points.

---

## 5) Utilisation en Point de Vente (POS)

### A. Créditer la carte via “Rendu monnaie (FCFA)”

1. Ouvrir le POS et démarrer une session
2. Créer/ouvrir une commande
3. **Sélectionner un client** (obligatoire)
4. Cliquer sur le bouton **Rendu monnaie (FCFA)**
5. Choisir la carte du client
6. Saisir le montant à créditer dans **Rendu monnaie**
7. Valider (“Mettre à jours les points”)

✅ Résultat attendu :

- le solde de la carte augmente
- une ligne d’historique est créée avec un libellé du type “Rendu monnaie: XX FCFA”

Erreurs fréquentes :

- **Aucun client** : “Veuillez sélectionner un client d’abord.”
- **Pas de carte** : le système peut refuser la mise à jour si aucune carte n’existe.

### B. Payer une commande avec la carte (moyen de paiement)

1. Dans le POS, sélectionner le client
2. Aller à l’écran de paiement
3. Choisir le moyen de paiement coché **Carte de fidélité**
4. Saisir le montant payé
5. Valider

✅ Résultat attendu :

- si le solde est suffisant : paiement accepté, solde diminue
- si solde insuffisant : message “Crédit insuffisant …”

---

## 6) Utilisation côté Ventes (commande)

### A. Paiement “Carte de fidélité” sur une commande

1. Créer une commande client
2. Choisir le mode de paiement **Carte de fidélité** (si proposé)
3. Confirmer la commande

✅ Résultat attendu :

- confirmation autorisée uniquement si le client a une carte et un solde suffisant
- le solde est diminué du montant de la commande
- un historique est créé

### B. Créditer la carte depuis la commande (bouton “Rendu monnaie”)

Sur une commande confirmée (état **Vente**), un bouton **Rendu monnaie** peut être visible.

1. Ouvrir la commande
2. Cliquer **Rendu monnaie**
3. Saisir le montant à créditer
4. Valider

✅ Résultat attendu : solde augmenté + historique.

---

## 7) Utilisation côté Comptabilité (paiement facture)

Quand vous enregistrez un paiement sur une facture avec un **journal** coché “Carte de fidélité” :

✅ Le système :

- vérifie que le client a une carte
- vérifie que le solde couvre le montant
- déduit automatiquement les points

Erreurs fréquentes :

- “Le client X n’a pas de carte de fidélité …”
- “Le montant … dépasse les points … disponibles …”

---

## 8) Contrôler l’historique (preuve du test)

Après un crédit ou une utilisation, aller dans la carte / historique de fidélité (Odoo standard) et vérifier :

- l’opération (description)
- le montant utilisé/crédité
- éventuellement le champ **Nom du POS** (si affiché)

✅ Résultat attendu : chaque mouvement important laisse une trace.

---

## 9) Check-list de test rapide (10 minutes)

1. Catégorie : définir Famille Fidélité = 1 point / 200 F
2. Produit : cocher “Éligible”
3. Client : vérifier qu’il a une carte
4. POS : vendre un produit éligible → vérifier que le client gagne des points (selon programme fidélité)
5. POS : payer partiellement en “Carte de fidélité” → solde diminue
6. POS : bouton “Rendu monnaie (FCFA)” → solde augmente
7. Historique : vérifier que les lignes sont créées

---

## 10) Emplacements pour captures d’écran

- [CAPTURE] Produit : section “Fidélité” (éligible + famille)
- [CAPTURE] Catégorie : “Famille Fidélité”
- [CAPTURE] Client : “A une carte de fidélité”
- [CAPTURE] POS : bouton “Rendu monnaie (FCFA)”
- [CAPTURE] Wizard : “Rendu monnaie - Carte fidélité”
- [CAPTURE] POS : paiement avec moyen “Carte de fidélité”
- [CAPTURE] Historique : mouvements de la carte
