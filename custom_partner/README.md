# Guide utilisateur — Partenaires & cartes de fidélité (module `custom_partner`)

Ce guide décrit **ce que voit l’utilisateur** dans Odoo après installation du module **Personnalisation des partenaires**.

> Objectif : améliorer la fiche client (Contacts) et mieux maîtriser l’utilisation des **cartes de fidélité** (code modifiable, identification client, et prévention de création automatique non désirée).

---

## 1) Pour qui ?

- **Administration / Back-office** : gestion des fiches clients (Contacts), remise client, responsables, identification.
- **Commercial / Ventes** : consultation des remises et infos client.
- **Responsable fidélité** : création/édition des cartes, suivi des points.
- **Caisse / POS** : dépend fortement des cartes existantes (voir point important ci-dessous).

---

## 2) Changements visibles dans Odoo

### A. Fiche client (Contacts)

Dans **Contacts → Contacts → (ouvrir un client)** :

1) Le champ **Étiquettes** est renommé en **Catégorie client**.

2) De nouveaux champs d’identification apparaissent près des informations légales :

- **ID client** (lecture seule) : identifiant automatiquement synchronisé avec le code de la carte de fidélité.
- **Code famille** (lecture seule)

3) Dans **Ventes & Achats** :

- **Responsable principal** (lecture seule)
- **Responsable secondaire** (lecture seule)

4) Un nouvel onglet **Remises & Taxes** :

- **Éligible à la remise**
- **Pourcentage de remise** (visible seulement si éligible)
- **Période** (Date début / Date fin, visible seulement si éligible)
- **Éligible à l’AIRSI** (affichage)

5) Un nouvel onglet **Cartes de fidélité** :

- liste des cartes rattachées au client (Code, Points, Date d’expiration, Programme)

---

## 3) Point important : création automatique de cartes (désactivée)

Avec ce module, la **création automatique** de cartes de fidélité depuis certaines actions (POS / Ventes) est **bloquée**.

✅ Conséquence pour les équipes :

- si vous voulez utiliser une carte au POS / en vente, il faut **créer la carte à l’avance** (ou s’assurer qu’elle existe déjà).

---

## 4) Workflow 1 — Gérer l’identifiant client via la carte de fidélité

### A. Créer / modifier le code de la carte

1. Aller dans l’application **Fidélité** (menu standard Odoo)
2. Ouvrir **Cartes de fidélité**
3. Créer une carte ou ouvrir une carte existante
4. Renseigner / modifier le champ **Code** (il est modifiable avec ce module)
5. Enregistrer

✅ Résultat attendu :

- le code de la carte est accepté si unique
- le champ **ID client** de la fiche Contact du client est automatiquement mis à jour avec ce même code

Erreurs fréquentes :

- **Code déjà utilisé** : le système refuse si le code n’est pas unique.

### B. Vérifier côté Contact

1. Ouvrir le client dans **Contacts**
2. Vérifier le champ **ID client**

✅ Résultat attendu : ID client = Code de la carte.

---

## 5) Workflow 2 — Paramétrer une remise client

1. Ouvrir le client dans **Contacts**
2. Aller à l’onglet **Remises & Taxes**
3. Cocher **Éligible à la remise**
4. Saisir le **Pourcentage de remise**
5. Vérifier / ajuster la **Date de début** et la **Date de fin**

✅ Résultat attendu :

- dès que “Éligible à la remise” est coché, la **Date de début** se remplit automatiquement avec la date du jour.

Bonnes pratiques :

- toujours définir une période claire (ex: remise promotionnelle)
- si la remise est permanente, convenir d’une règle interne (ex: date de fin très éloignée) ou laisser le champ fin géré selon vos procédures.

---

## 6) Workflow 3 — Consulter les cartes de fidélité d’un client

1. Ouvrir le client dans **Contacts**
2. Onglet **Cartes de fidélité**

✅ Résultat attendu :

- vous voyez toutes les cartes rattachées au client, avec le code, les points, la date d’expiration et le programme.

---

## 7) Workflow 4 — Suivi AIRSI (information)

1. Ouvrir le client dans **Contacts**
2. Onglet **Remises & Taxes**
3. Vérifier **Éligible à l’AIRSI**

✅ Résultat attendu :

- le statut est visible dans l’onglet.

> Note : l’impact exact sur la facturation/taxes dépend des autres modules de votre base (ex: modules qui ajoutent/retirent une taxe AIRSI selon ce statut).

---

## 8) Check-list de test rapide (10 minutes)

1) Ouvrir un client → vérifier :

- “Catégorie client” (au lieu d’Étiquettes)
- “ID client” et “Code famille” visibles (lecture seule)
- onglet “Remises & Taxes” visible
- onglet “Cartes de fidélité” visible

2) Créer/ouvrir une carte de fidélité :

- modifier le **Code**
- enregistrer
- vérifier que le **Contact** du client a bien “ID client” = code

3) Remise :

- cocher “Éligible à la remise”
- vérifier que la date de début se remplit automatiquement
- saisir un pourcentage

4) Contrôle anti-duplicat :

- tenter d’attribuer le même code à 2 cartes → doit être refusé

---

## 9) Emplacements pour captures d’écran

- [CAPTURE] Contact : champ “Catégorie client” (ex-Étiquettes)
- [CAPTURE] Contact : champs “ID client” + “Code famille”
- [CAPTURE] Contact : onglet “Remises & Taxes” (remise + période)
- [CAPTURE] Contact : onglet “Cartes de fidélité” (liste)
- [CAPTURE] Carte de fidélité : champ “Code” modifiable
- [CAPTURE] Message d’erreur : code de carte en doublon
