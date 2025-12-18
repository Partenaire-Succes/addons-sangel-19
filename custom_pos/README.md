# Guide utilisateur — Point de Vente (module `custom_pos`)

Ce guide décrit **ce que voit et fait l’utilisateur** dans Odoo après installation du module **Personnalisation du Point de vente**.

> Objectif : sécuriser certaines ventes au POS (rupture de stock, remises), éviter les erreurs de caisse, et améliorer l’affichage (reçu, solde fidélité, libellés).

---

## 1) Pour qui ?

- **Caissière / Caisse (POS)** : encaissement et validation des ventes.
- **Responsable caisse** : autorisations ponctuelles (code d’accès) et supervision.
- **Responsable magasin / DSI** : paramétrage, gestion des droits.

---

## 2) Ce qui change (visible dans le POS)

### A. Sécurité lors du paiement

Au moment de cliquer **Paiement** :

1) **Quantité nulle interdite**

- Si une ligne a une quantité = 0, la commande ne peut pas être validée.

2) **Double remise interdite**

- Un même produit ne peut pas avoir **à la fois** :
  - une **remise sur la ligne** (ex: 10%),
  - et une **promotion / remise** déjà appliquée via une ligne spéciale (souvent une ligne à prix négatif ou “récompense/promo”).

3) **Autorisation requise** en cas de :

- **produit en rupture de stock** (stock ≤ 0), et/ou
- **commande avec remise/promotion**

Dans ces cas, le POS peut demander un **code d’accès** (si configuré) avant de continuer.

---

### B. Fidélité : affichage du solde au paiement

Sur l’écran de paiement, si :

- un **client** est sélectionné,
- et qu’il a des **points fidélité**,

alors un encart affiche le **solde des points**.

---

### C. Reçu : en-tête et pied de page

Sur le ticket (reçu) :

- le nom de la **caisse / point de vente** peut s’afficher dans l’en-tête,
- la mention “Powered by Odoo” est supprimée du pied de page.

---

### D. Ouverture de session caisse

Dans la fenêtre d’ouverture :

- le libellé **Fond de caisse** est utilisé.

> Selon votre configuration, un montant initial peut apparaître : si ce montant ne correspond pas à vos procédures, saisissez votre fond réel.

### E. Boutons rapides de remise (Preset Remise)

Sur l'écran de paiement, sous le bouton **Client**, des boutons rapides permettent d'appliquer rapidement des remises prédéfinies :

- Boutons affichant des pourcentages (ex: **10%**, **20%**, **45%**)
- Un clic applique directement le remise au produit sélectionné
- Évite de devoir taper manuellement la percentage
- Configurable par la direction (ajouter/retirer des percentages)

✅ Avantage :

- Gain de temps au caisse
- Remises cohérentes et configurées
- Facilité d'accès pour les remises fréquentes

---

### A. Définir le code d’accès “rupture de stock / remises”

1. Aller dans **Point de Vente → Configuration → Points de vente**
2. Ouvrir la caisse concernée
3. Rechercher le paramètre **Code d’accès pour rupture de stock**
4. Saisir un code (ex: code interne responsable)
5. **Enregistrer**

✅ Résultat attendu :

- quand une vente nécessite une autorisation, le POS peut demander ce code.

Bonnes pratiques :

- choisir un code connu uniquement des responsables
- changer le code en cas de départ d’un responsable

---

### B. Configurer les boutons rapides de remise

1. Aller dans **Point de Vente → Configuration → Points de vente**
2. Ouvrir la caisse concernée
3. Rechercher le paramètre **Quick Remise Buttons** (sous "Code d'accès pour rupture de stock")
4. Modifier les valeurs (ex: `10,20,45` pour avoir des boutons 10%, 20%, 45%)
5. **Enregistrer**

Bonnes pratiques :

- Utiliser des valeurs entre 0 et 100
- Séparer par des virgules (ex: `5,10,20,45`)
- Les doublons sont automatiquement supprimés et triés
- Laisser vide pour désactiver les boutons rapides

---

### C. Droits (qui peut contourner le contrôle)

Le module ajoute des profils liés au POS (exemples) :

- **Caissiere**
- **Responsable des caisse**
- **Responsable des Magasin**
- **DSI**

En pratique, certains profils “responsables” peuvent passer plus facilement (ou ne pas être bloqués) lors des contrôles.

1. Aller dans **Paramètres → Utilisateurs et sociétés → Utilisateurs**
2. Ouvrir l’utilisateur
3. Dans les **Droits d’accès**, chercher la catégorie **POS Personnalisé**
4. Choisir le niveau adapté (Caissiere / Responsable / …)
5. **Enregistrer**

✅ Résultat attendu :

- les caissières sont contrôlées,
- les responsables peuvent autoriser au besoin.

---

## 4) Workflows (côté caisse)

### Workflow 1 — Vente avec produit en rupture de stock

1. Au POS, ajouter un produit
2. Si le produit est en rupture (stock ≤ 0)
3. Cliquer **Paiement**

✅ Résultat attendu :

- un message indique que le produit est en rupture
- si un **code d’accès** est configuré, le POS demande le code

Cas possibles :

- **Code correct** → vous pouvez continuer
- **Code incorrect** → message “Code incorrect” et la vente est annulée
- **Pas de code configuré** → la vente est bloquée avec un message d’information

---

### Workflow 2 — Vente avec remise (autorisation)

Une remise peut être détectée par :

- une **remise %** sur une ligne,
- ou une **ligne promotionnelle** (ex: ligne à prix négatif / programme promo).

1. Appliquer une remise (selon vos habitudes)
2. Cliquer **Paiement**

✅ Résultat attendu :

- le POS demande une autorisation (code) pour continuer.

---

### Workflow 2b — Appliquer une remise rapide via boutons prédéfinis

1. Au POS, ajouter un produit à la commande
2. Sur l'écran de **Paiement**, cliquer sur le bouton de remise désiré (ex: **45%**)

✅ Résultat attendu :

- la remise est appliquée au produit sélectionné (ou le dernier produit ajouté)
- le total se met à jour automatiquement
- le produit est marqué comme ayant une remise

---

Symptôme : au moment de **Paiement**, message : **❌ Double remise interdite**.

1. Lire la liste des produits indiqués
2. Pour chaque produit :
   - soit **retirer la remise %** sur la ligne,
   - soit **retirer la ligne de promotion/remise** (ligne promo)
3. Revenir à **Paiement**

✅ Résultat attendu :

- la commande passe si une seule remise est appliquée par produit.

---

### Workflow 4 — Erreur “Quantité nulle non autorisée”

Symptôme : au moment de **Paiement**, message : “Quantité nulle non autorisée”.

1. Retourner sur l’écran des produits
2. Corriger la ligne concernée (mettre une quantité **> 0**) ou supprimer la ligne
3. Revenir à **Paiement**

✅ Résultat attendu :

- la commande peut être validée.

---

### Workflow 5 — Afficher le solde de points fidélité au paiement

1. Au POS, sélectionner un **Client**
2. Aller sur l’écran **Paiement**

✅ Résultat attendu :

- un encart affiche **Solde: Point de fidelite** avec le nombre de points.

Si rien ne s’affiche :

- vérifier qu’un client est bien sélectionné
- vérifier que le client a une carte / des points dans le module Fidélité

---

### Workflow 6 — Vérifier le ticket (reçu)

1. Finaliser une vente
2. Imprimer / afficher le ticket

✅ Résultat attendu :

- le nom de la **caisse** apparaît dans l’en-tête (si configuré)
- le pied “Powered by Odoo” n’apparaît pas

---

## 5) Point d’attention : Promotion “3=4” (selon votre organisation)

Le module contient une base technique pour une promo type **“3 achetés = 1 offert”** (appel serveur dédié).

- Si votre équipe **utilise** ce type de promo, mais que vous ne voyez rien au POS : demandez à l’administrateur (il peut y avoir un paramétrage/activation à compléter).

---

## 6) Check-list de test rapide (10–15 minutes)

1) **Paramétrage**

- vérifier qu’un code est saisi dans la configuration du POS

2) **Rupture de stock**

- tenter de vendre un produit en rupture
- vérifier : blocage + demande de code (si code configuré)

3) **Remise**

- appliquer une remise
- vérifier : demande de code

4) **Double remise**

- mettre une remise % + une promo sur le même produit
- vérifier : message “Double remise interdite”

5) **Quantité nulle**

- créer une ligne à quantité 0
- vérifier : blocage “Quantité nulle non autorisée”

6) **Fidélité**

- sélectionner un client avec points
- vérifier : affichage du solde au paiement

7) **Ticket**

- vérifier : nom du POS sur le reçu + absence de “Powered by Odoo”

---

## 7) Emplacements pour captures d’écran

- [CAPTURE] Configuration POS : champ “Code d’accès pour rupture de stock”- [CAPTURE] Configuration POS : champ "Quick Remise Buttons"
- [CAPTURE] POS Paiement : boutons rapides de remise (10%, 20%, 45%)- [CAPTURE] POS : message de rupture de stock + demande de code
- [CAPTURE] POS : message “Double remise interdite”
- [CAPTURE] POS : message “Quantité nulle non autorisée”
- [CAPTURE] POS : encart solde fidélité sur écran paiement
- [CAPTURE] Reçu : nom de la caisse dans l’en-tête
- [CAPTURE] Reçu : pied de page sans “Powered by Odoo”
