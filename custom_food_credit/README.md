# Guide utilisateur — Crédit alimentaire & Compte client (module `custom_food_credit`)

Ce guide explique **comment paramétrer**, **utiliser** et **tester** le crédit alimentaire et la limite de crédit (compte client) dans Odoo, côté utilisateur final.

> Objectif métier : une entreprise cliente attribue chaque mois un **montant de crédit** à ses employés (bénéficiaires). Les employés peuvent consommer ce crédit en **Point de Vente (POS)** et/ou via **Ventes**. L’utilisation génère des **détails de consommation** qui peuvent être **facturés**.

---

## 1) Profils concernés

- **Administrateur / Responsable commercial** : paramétrage des entreprises, des montants, des moyens de paiement POS.
- **Gestionnaire crédit** : génération mensuelle des crédits, suivi des consommations, clôture.
- **Caissier (POS)** : encaissement en “Crédit alimentaire” ou “Compte client”.
- **Commercial (Ventes)** : confirmation de commande avec paiement “Crédit alimentaire” / “Compte client”.
- **Comptable** : génération des factures de consommation et contrôle de l’impression.

---

## 2) Les deux mécanismes (en clair)

### A. Crédit alimentaire (mensuel)

- Le crédit alimentaire est porté par une **entreprise** (client société).
- Les **employés** sont des contacts rattachés à l’entreprise (contacts “enfants”).
- Un crédit mensuel est généré et crée des **lignes** pour chaque employé, avec un **solde**.
- À chaque paiement POS / commande, le solde diminue et une trace “détails consommations” s’alimente.

### B. Limite de crédit (compte client)

- La limite de crédit est un **plafond** autorisé pour un client.
- Chaque utilisation (POS / ventes) augmente le “consommé”, et un **solde disponible** est calculé.
- Un historique d’opérations est conservé.

---

## 3) Où trouver les menus

Ces menus sont ajoutés dans : **Ventes → Configuration**

- **Crédit alimentaire** (Gestion des crédits alimentaires)
- **Limite credit** (Gestion des limites)

---

## 4) Paramétrage initial (Administrateur)

### A. Paramétrer une entreprise “Crédit alimentaire”

1. Ouvrir **Contacts → Contacts**
2. Ouvrir la fiche de la société (type société)
3. Aller à l’onglet **Credt** (oui, orthographe telle quelle dans l’écran)
4. Dans le bloc **Credit Alimentaire** :
   - cocher **A un credit Alimentaire**
   - renseigner **Credit Alimentaire** (montant mensuel)

✅ Résultat attendu : la société devient éligible à la génération mensuelle des crédits.

### B. Rattacher les employés à l’entreprise

1. Ouvrir chaque employé dans **Contacts**
2. Vérifier que l’employé a bien une **Société parente** (Parent)
3. Vérifier que l’employé est **actif**

✅ Résultat attendu : lors de la génération mensuelle, une ligne de crédit est créée par employé actif.

### C. Paramétrer la “Limite de crédit” (Compte client)

1. Ouvrir **Contacts → Contacts**
2. Sur le client concerné, onglet **Credt**
3. Dans le bloc **Limite de credit** :
   - cocher **A une limite de credit**
   - renseigner **Limite de credit**

✅ Résultat attendu : une fiche “Limite credit” est automatiquement disponible dans le menu “Limite credit”.

### D. Paramétrer les moyens de paiement POS

Chemin : **Point de Vente → Configuration → Moyens de paiement**

Sur chaque moyen de paiement concerné, vous verrez :

- **Credit Alimentaire**
- **En cours / Compte client**

Recommandation pratique :

- créer/nommer un moyen de paiement “Crédit Alimentaire” et cocher **Credit Alimentaire**
- créer/nommer un moyen de paiement “Compte client” et cocher **En cours / Compte client**

✅ Résultat attendu : le POS bloquera automatiquement les paiements si le client n’est pas autorisé.

---

## 5) Workflow 1 — Générer le crédit alimentaire du mois

### Option 1 : depuis la liste (rapide)

1. Aller à **Ventes → Configuration → Crédit alimentaire**
2. Cliquer sur **Générer Crédits + Lignes**
3. Confirmer

✅ Résultat attendu :

- un crédit par entreprise éligible (si pas déjà créé pour le mois)
- des lignes employé générées automatiquement
- une notification “Génération des crédits terminée”

### Option 2 : depuis un crédit (wizard Mois/Année)

1. Ouvrir un crédit en **Brouillon**
2. Cliquer sur **Générer Crédits Alimentaires**
3. Choisir **Mois**, **Année**, (option) **Écraser les crédits existants**, et la liste de **Sociétés**
4. Cliquer **Générer**

✅ Résultat attendu :

- si “Écraser…” est désactivé : les crédits déjà existants ne sont pas modifiés
- si “Écraser…” est activé : le crédit du mois peut être mis à jour et ses lignes régénérées

---

## 6) Workflow 2 — Valider / clôturer un crédit

Dans un crédit (formulaire) :

- **Soumettre pour validation** : passe l’état de **Brouillon** à **En cours**
- **Clôturer** : passe l’état à **Terminé**

✅ Points importants :

- sans lignes d’employés, la validation est refusée (“Vous devez d'abord créer les lignes des clients.”)
- un crédit non brouillon ne peut pas être supprimé.

---

## 7) Workflow 3 — Utiliser le crédit alimentaire au POS

### A. Paiement POS “Crédit alimentaire”

1. Ouvrir le POS
2. Créer une commande
3. **Sélectionner un client**
4. Aller au paiement
5. Choisir le moyen de paiement coché **Credit Alimentaire**
6. Valider le paiement

✅ Résultat attendu :

- si le client n’est pas autorisé : message “Ce client n'a pas accès au crédit alimentaire.”
- si aucun crédit valide : message “Aucun crédit alimentaire valide pour ce client.”
- si solde insuffisant : message “Crédit insuffisant ! Disponible: … FCFA”
- sinon : paiement accepté, le “consommé” augmente et un détail est ajouté (POS: date – ticket – montant)

### B. Paiement POS “Compte client” (limite de crédit)

Même principe, mais avec le moyen de paiement coché **En cours / Compte client**.

✅ Résultat attendu :

- si le client n’est pas autorisé : “Ce client n'a pas accès au Compte client.”
- si solde insuffisant : “Crédit insuffisant ! Disponible: … FCFA”
- une opération est créée dans l’historique de la limite.

---

## 8) Workflow 4 — Utiliser en Ventes (commande)

Sur une commande client :

- champ **Mode de payment** :
  - **Credit alimentaire** → contrôle du solde et déduction à la confirmation
  - **Compte client** → contrôle du solde limite et déduction à la confirmation
  - **Autre** → comportement standard

### A. Confirmation avec “Crédit alimentaire”

1. Créer une commande
2. Sélectionner le client
3. Choisir **Mode de payment = Credit alimentaire**
4. Confirmer

✅ Résultat attendu :

- si pas de crédit : message d’erreur bloquant
- si solde insuffisant : message d’erreur bloquant
- sinon : le consommé augmente, et un détail “GROS/(1/2 GROS): …” est enregistré

### B. Confirmation avec “Compte client”

Idem mais avec **Mode de payment = Compte client**.

✅ Résultat attendu :

- consommation de la limite + création d’une opération “Gros & 1/2 Gros - …”

### C. Annulation d’une commande

Si une commande payée via crédit alimentaire / compte client est annulée, le module tente de **restaurer** le solde (crédit/limite) et crée une opération négative pour la limite.

---

## 9) Workflow 5 — Générer les factures de consommation

Ce workflow sert à facturer l’entreprise cliente selon les consommations (montants utilisés).

1. Aller dans **Ventes → Configuration → Crédit alimentaire**
2. Ouvrir un crédit (souvent à l’état **En cours**)
3. Cliquer **Generer les factures**
4. Renseigner :
   - **Date de début** (forcée au 1er jour du mois)
   - **Date de fin** (forcée au dernier jour du mois)
   - **Date de facture**
   - **Journal** (journal de vente)
   - **Produit Crédit Alimentaire** (par défaut “Crédit Alimentaire”)
5. (Optionnel) Cliquer **Aperçu**
6. Cliquer **Générer les Factures**

✅ Résultat attendu :

- une facture par entreprise (si non déjà facturée)
- des lignes par employé consommateur (montant > 0)
- sur l’impression facture : une colonne **Details Consommations** peut apparaître avec les détails POS / commandes

---

## 10) Suivi “Limite credit” (compte client)

Chemin : **Ventes → Configuration → Limite credit**

Vous verrez :

- **Limite** (plafond)
- **Consommée**
- **Solde disponible**

Boutons utiles :

- **Voir les details** : ouvre la fiche et l’onglet “Liste des Operations”
- **Mettre à jour le crédit** : ouvre un wizard de mise à jour

---

## 11) Check-list de test (end-user) — 15 minutes

1. Contacts : sur une société, cocher “A un credit Alimentaire” + montant mensuel
2. Contacts : créer 2 employés rattachés à la société
3. POS : créer un moyen de paiement “Crédit Alimentaire” (case cochée)
4. Génération : **Ventes → Configuration → Crédit alimentaire** → “Générer Crédits + Lignes”
5. Ouvrir le crédit créé : vérifier que les lignes employés existent et ont un solde
6. POS : sélectionner un employé, payer une commande avec “Crédit Alimentaire”
7. Revenir sur le crédit : vérifier que “Montants consommés” a augmenté et que “Factures” (détails) se remplit
8. Facturation : “Generer les factures” → Aperçu → Générer → vérifier la facture et la colonne “Details Consommations”
9. (Option) Limite : activer “A une limite de credit” sur un client, payer au POS via “Compte client” → vérifier l’historique d’opérations

---

## 12) Emplacements pour captures d’écran

- [CAPTURE] Contact société : onglet “Credt” → bloc “Credit Alimentaire”
- [CAPTURE] POS : moyen de paiement (cases Credit Alimentaire / Compte client)
- [CAPTURE] Liste “Crédit alimentaire” : bouton “Générer Crédits + Lignes”
- [CAPTURE] Crédit (formulaire) : lignes employés + solde
- [CAPTURE] POS : message “Client requis / Accès refusé / Crédit insuffisant”
- [CAPTURE] Wizard “Générer les Factures” + écran Aperçu
- [CAPTURE] Facture imprimée : colonne “Details Consommations”
- [CAPTURE] Limite credit : liste + fiche + opérations
