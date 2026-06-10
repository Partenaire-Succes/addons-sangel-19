# Manuel d'Utilisation — Suite SANGEL Odoo 19

**Version** : 19.0  
**Langue** : Français  
**Date** : Mai 2026  
**Destinataires** : Utilisateurs métier, superviseurs, administrateurs

---

## Table des matières

1. [Point de Vente (custom_pos)](#1-point-de-vente-custom_pos)
2. [Promotions et Tarifs (custom_sales)](#2-promotions-et-tarifs-custom_sales)
3. [Gestion des Stocks (custom_stock)](#3-gestion-des-stocks-custom_stock)
4. [Programme de Fidélité (custom_loyalty)](#4-programme-de-fidélité-custom_loyalty)
5. [Crédit Alimentaire (custom_food_credit)](#5-crédit-alimentaire-custom_food_credit)
6. [Intégration SAGE X3 (custom_api_sage_x3)](#6-intégration-sage-x3-custom_api_sage_x3)
7. [Achats (custom_purchase)](#7-achats-custom_purchase)
8. [Comptabilité (custom_account)](#8-comptabilité-custom_account)
9. [Partenaires (custom_partner)](#9-partenaires-custom_partner)
10. [Rapports et Analyses (custom_reports)](#10-rapports-et-analyses-custom_reports)
11. [Rapport de Reliquats (custom_reliquat_report)](#11-rapport-de-reliquats-custom_reliquat_report)
12. [Multi-Codes-Barres Produits (custom_multi_barcode_for_products)](#12-multi-codes-barres-produits-custom_multi_barcode_for_products)
13. [Suivi des Prix (custom_price_change_tracker)](#13-suivi-des-prix-custom_price_change_tracker)
14. [Tableau de Bord Administration (dashboard_management_administration)](#14-tableau-de-bord-administration-dashboard_management_administration)
15. [Certification FNE (fne_certification)](#15-certification-fne-fne_certification)
16. [Masquage de Menus (hide_menu_user)](#16-masquage-de-menus-hide_menu_user)

---

## Conventions du document

| Symbole | Signification |
|---|---|
| **[Bouton]** | Bouton cliquable à l'écran |
| `Chemin › Sous-menu` | Navigation dans le menu |
| ⚠️ | Avertissement important |
| ℹ️ | Information utile |
| 🔒 | Action réservée à un groupe spécifique |

---

## 1. Point de Vente (`custom_pos`)

### 1.1 Accès et rôles

La caisse SANGEL dispose de **5 niveaux d'accès** :

| Rôle | Droits principaux |
|---|---|
| **Caissière** | Saisie des ventes, encaissement |
| **Superviseur** | Supervision, corrections, validations |
| **Assistant Magasin** | Ventes, stocks, réceptions |
| **Responsable Magasin** | Accès complet magasin |
| **Commercial** | Ventes et comptes clients |

---

### 1.2 Rapport de mode de paiement

**Accès** : `Point de Vente › Rapport de mode paiement`  
**Rôles** : Superviseur, Responsable Magasin, DSI IT

Ce rapport permet d'analyser les encaissements par mode de paiement sur une période.

**Étapes :**

1. Aller dans `Point de Vente › Rapport de mode paiement`
2. Remplir le formulaire :
   - **Date début** *(obligatoire)* — Date de début de la période
   - **Date fin** *(obligatoire)* — Date de fin de la période
   - **Catégories client** *(optionnel)* — Filtrer par catégorie de clients
   - **Mode de paiement** *(optionnel)* — Filtrer par mode de paiement spécifique
3. Cliquer sur **[Télécharger le rapport PDF]** pour générer le PDF
4. Cliquer sur **[Fermer]** pour annuler

---

### 1.3 Rapport des validations manager

**Accès** : `Point de Vente › Rapport des validations`  
**Rôles** : Superviseur uniquement

Ce rapport liste toutes les validations effectuées par les managers sur les opérations sensibles en caisse (remises, modifications de prix, etc.).

**Étapes :**

1. Aller dans `Point de Vente › Rapport des validations`
2. Remplir le formulaire :
   - **Date du** — Date de début
   - **Date au** — Date de fin
   - **Configurations** — Sélectionner une ou plusieurs caisses (optionnel)
3. Cliquer sur **[Télécharger le rapport]** pour générer

---

### 1.4 Import des points de fidélité (Excel)

**Accès** : `Point de Vente › Import Excel Points Fidélité`  
**Rôles** : Manager POS

Permet d'importer en masse des points de fidélité depuis un fichier Excel.

**Étapes :**

**Étape 1 — Télécharger le gabarit**
1. Ouvrir l'assistant d'import
2. Cliquer sur **[Télécharger le gabarit]** pour obtenir le fichier Excel modèle
3. Remplir le fichier avec les données de points

**Étape 2 — Charger le fichier**
1. Cliquer sur le champ **Fichier** et sélectionner le fichier Excel rempli
2. Cliquer sur **[Charger le fichier]**
3. Le système affiche un résumé :
   - **Lignes OK** — Nombre de lignes valides
   - **Lignes en erreur** — Nombre de lignes avec problèmes

**Étape 3 — Confirmer l'import**
1. Vérifier les lignes chargées (statut affiché en couleur)
2. Si satisfaisant, cliquer sur **[Confirmer la mise à jour]**
3. Les points sont mis à jour sur les cartes de fidélité

> ⚠️ Le bouton **[Confirmer la mise à jour]** n'est visible qu'après chargement du fichier.

---

### 1.5 Fonctionnalités en caisse (POS)

#### Ouverture du tiroir-caisse
- Raccourci clavier : **Alt + C**
- Action : Ouvre manuellement le tiroir-caisse sans transaction

#### Conversion multi-devises
- Lors d'un paiement en devise étrangère, une popup s'affiche automatiquement
- Elle indique le montant converti en devise locale (XOF)
- Les taux de change sont récupérés en temps réel via `/pos/active_currencies`

#### Taxe AIRSI automatique
- La taxe AIRSI est appliquée **automatiquement** selon la combinaison client + produit
- Aucune action manuelle requise

#### Promotion 3×4
- Le système vérifie automatiquement la règle « 3 achetés = 4 livrés » à chaque ajout de produit
- La remise s'applique sans action utilisateur

#### Code d'accès manager
- Certaines opérations sensibles (remise manuelle, modification de prix) demandent un code d'accès manager
- Le superviseur saisit son code pour valider l'opération

---

## 2. Promotions et Tarifs (`custom_sales`)

### 2.1 Accès

**Accès** : `Point de Vente › Promotions Sangel`  
**Rôles** : Point Control

---

### 2.2 Créer une promotion

**Étapes :**

1. Aller dans `Point de Vente › Promotions Sangel`
2. Cliquer sur **[Nouveau]**
3. Remplir l'en-tête :

| Champ | Type | Description |
|---|---|---|
| **Nom** | Texte | Code de la promotion (ex : *PROMO-2024-01*) |
| **Sociétés** | Multi-sélection | Sociétés concernées |
| **Date début** | Date | Début de validité |
| **Date fin** | Date | Fin de validité |

4. Ajouter les lignes de produits dans l'onglet **Lignes de promotion** :

| Champ | Description |
|---|---|
| **Produit** | Produit concerné (obligatoire) |
| **Remise (%)** | Pourcentage de remise — *Mode 1* |
| **Promo HT** | Prix promotionnel hors taxe — *Mode 2* |
| **Promo TTC** | Prix promotionnel toutes taxes comprises — *Mode 3* |

> ℹ️ **Calcul automatique des prix** : Saisir l'un des 3 champs calcule automatiquement les deux autres.  
> - Mode 1 (Remise %) → calcul automatique du Promo HT  
> - Mode 2 (Promo HT) → calcul automatique de la Remise % et du Promo TTC  
> - Mode 3 (Promo TTC) → calcul automatique du Promo HT et de la Remise %

Champs calculés (lecture seule) :
- **Prix HT** / **Prix TTC** — Prix catalogue du produit
- **Coefficient** — Ratio prix de vente / coût
- **Taux de marque** — Marge en pourcentage
- **Stock disponible** / **Stock prévisionnel** — Niveaux de stock actuels

5. Cliquer sur **[Sauvegarder]**

---

### 2.3 Rechercher et filtrer les promotions

Dans la liste des promotions, les filtres disponibles sont :

| Filtre | Description |
|---|---|
| **Promotions actives** | Affiche uniquement les promos actives |
| **Actives en POS** | Promos applicables en caisse |
| **Archivées** | Promos désactivées |
| **Regrouper par Date début** | Regroupe par date de démarrage |

---

### 2.4 Modifier une promotion existante

1. Ouvrir la promotion depuis la liste
2. Cliquer sur **[Modifier]**
3. Mettre à jour les champs souhaités
4. Cliquer sur **[Sauvegarder]**

> ⚠️ Modifier une promotion active impacte immédiatement les prix en caisse POS si "Actif en POS" est coché.

---

## 3. Gestion des Stocks (`custom_stock`)

### 3.1 Inventaire physique

**Accès** : `Inventaire › Ajustements › Inventaire physique`  
**Rôles** : Assistant Magasin, Responsable Magasin, DSI IT

#### Cycle de vie d'un inventaire

```
Brouillon  ──►  En cours  ──►  Terminé
  (draft)    (in_progress)    (done)
```

#### Créer un inventaire

1. Cliquer sur **[Nouveau]**
2. Remplir les informations générales :

| Champ | Description |
|---|---|
| **Nom** | Intitulé de l'inventaire |
| **Mode** | *Normal* (avec codes) ou *Libre* (sans contrainte) |
| **Catégorie de code** | Catégorie de codification (obligatoire si Mode = Normal) |
| **Codes inventaire** | Codes spécifiques (obligatoire si Mode = Normal) |
| **Équipe inventaire** | Équipe responsable du comptage (obligatoire si Mode = Normal) |
| **Date** | Date de l'inventaire |
| **Société** | Société concernée |

3. Cliquer sur **[Générer les articles]** pour peupler les lignes de produits
4. Cliquer sur **[Sauvegarder]**

#### Soumettre pour validation

1. Vérifier que les informations sont correctes
2. Cliquer sur **[Soumettre pour validation]** — L'inventaire passe en **En cours**

#### Saisir les quantités physiques

Dans l'onglet **Lignes d'inventaire physique** :

| Colonne | Description |
|---|---|
| **Produit** | Référence produit |
| **Qté physique** | *(Saisie manuelle)* Quantité comptée |
| **Qté différence** | Écart automatique (vert = surplus, rouge = manquant) |
| **Prix/Unité (PMP)** | Coût moyen pondéré |
| **Valorisation** | Valeur calculée |
| **Vérifié par** | Agent qui a compté |

#### Actualiser les données

- Cliquer sur **[Actualiser Stock et Prix]** pour rafraîchir les quantités théoriques

> ⚠️ Cette action demande une **confirmation** car elle met à jour les données depuis Odoo.

#### Valider l'inventaire 🔒

1. Vérifier tous les écarts
2. Cliquer sur **[Valider l'inventaire]** — Réservé au **Superviseur**
3. Le système crée automatiquement les mouvements d'ajustement de stock
4. Le garde-fou AVCO vérifie que les écarts de coût ne dépassent pas ±10 M FCFA

#### Imprimer

- **[Imprimer Inventaire]** — Disponible après validation (état Terminé)
- **[Imprimer fiche de comptage]** — Disponible en état Brouillon (fiche vierge pour le comptage)

#### Annuler un inventaire en cours

- Cliquer sur **[Annuler]** pour repasser en état Brouillon

---

### 3.2 Import de stock depuis Excel

**Accès** : `Inventaire › Ajustements › Import Stock Excel`

#### Étapes d'import produits

1. Aller dans l'assistant d'import
2. Renseigner :
   - **Société** — Société cible
   - **Entrepôt** — Entrepôt de destination
   - **Emplacement** — Emplacement de destination

3. Cliquer sur **[Charger Produits]** et sélectionner le fichier Excel

4. Vérifier les lignes chargées dans l'onglet **Produits** :

| Colonne | Description |
|---|---|
| **Code produit** | Référence interne |
| **Produit** | Désignation |
| **Statut** | Résultat de la correspondance |
| **Quantité** | Qté à ajuster |
| **Coût** | Coût unitaire |
| **Trouvé** | Produit identifié dans Odoo (oui/non) |

5. Cliquer sur **[Confirmer]** pour appliquer l'import

> ℹ️ L'onglet **Contacts** permet également d'importer des partenaires (bouton **[Charger Contacts]**).

---

### 3.3 Réception directe fournisseur

**Accès** : `Inventaire › Opérations › Réception directe` (ou via bouton contextuel)  
**Rôles** : Assistant Magasin, Responsable Magasin

Permet de créer une réception sans bon de commande préalable.

**Étapes :**

1. Ouvrir l'assistant de réception directe
2. Remplir l'en-tête :

| Champ | Description |
|---|---|
| **Fournisseur** | Partenaire fournisseur (optionnel) |
| **Date prévue** | Date de réception (obligatoire) |
| **Emplacement dest.** | Emplacement de destination (obligatoire) |
| **Réf. SAGE** | Référence SAGE X3 (optionnel) |
| **Notes** | Commentaire libre |

3. Ajouter les lignes de produits :

| Champ | Description |
|---|---|
| **Produit** | Produit reçu (obligatoire) |
| **Quantité** | Quantité reçue (obligatoire) |
| **Unité de mesure** | Unité |
| **Prix unitaire** | Coût actuel (lecture seule) |
| **Nouveau prix** | *(optionnel)* Mettre à jour le coût si différent |

4. Le **Montant total** se calcule automatiquement
5. Cliquer sur **[Valider la réception]** — Demande une confirmation

> ⚠️ Cette action est **irréversible**. Le stock est mis à jour immédiatement.

---

### 3.4 Retour fournisseur

**Accès** : `Inventaire › Opérations › Nouveau retour fournisseur`  
**Rôles** : Superviseur, Assistant Magasin, Responsable Magasin

**Étapes :**

1. Ouvrir l'assistant de retour fournisseur
2. Remplir :

| Champ | Description |
|---|---|
| **Fournisseur** | Partenaire fournisseur (obligatoire) |
| **Date prévue** | Date du retour |
| **Référence externe** | Référence document fournisseur |
| **Emplacement source** | Entrepôt d'origine |
| **Générer avoir** | Cocher pour créer automatiquement un avoir comptable |
| **Notes** | Observations |

3. Ajouter les lignes de retour :

| Champ | Description |
|---|---|
| **Produit** | Produit à retourner (obligatoire) |
| **Stock disponible** | Quantité disponible (lecture seule) |
| **Quantité à retourner** | Quantité à renvoyer (obligatoire) |
| **Prix unitaire** | Coût unitaire |

4. Cliquer sur **[Créer le bon de retour]** — Demande une confirmation

> ℹ️ Si **Générer avoir** est coché, un avoir comptable est créé automatiquement après validation.

#### Historique des retours fournisseur

**Accès** : `Inventaire › Opérations › Historique retours fournisseur`  
Affiche la liste de tous les retours fournisseurs passés avec filtres.

---

## 4. Programme de Fidélité (`custom_loyalty`)

### 4.1 Familles de fidélité

Les familles définissent le **barème de points** accordés aux clients.

**Accès** : `Configuration › Fidélité › Familles`

| Champ | Description |
|---|---|
| **Nom** | Nom de la famille (calculé automatiquement) |
| **Points gagnés** | Nombre de points accordés par palier |
| **Seuil de montant** | Montant d'achat requis pour gagner les points |
| **Catégories de produits** | Produits éligibles à cette famille |
| **Actif** | Activer/désactiver la famille |

**Exemple** : Famille "Standard" — 1 point pour 200 FCFA d'achat.

---

### 4.2 Mise à jour des points fidélité

**Accès** : Depuis la fiche client ou l'assistant dédié

**Étapes :**

1. Ouvrir l'assistant de mise à jour des points
2. Renseigner :
   - **Client** — Partenaire concerné
   - **Carte de fidélité** — Sélectionner la carte du client (filtré par client, points > 0)
   - **Points** — Points à ajuster
3. Cliquer sur **[Confirmer]** pour appliquer

> ℹ️ En caisse POS, les points sont accordés **automatiquement** après chaque paiement validé, selon la famille de fidélité du client.

---

### 4.3 Import de cartes de fidélité

Permet d'importer en masse les cartes de fidélité existantes.

**Étapes :**
1. Préparer le fichier Excel avec les colonnes requises
2. Ouvrir l'assistant d'import
3. Charger le fichier et confirmer

---

## 5. Crédit Alimentaire (`custom_food_credit`)

### 5.1 Présentation

Le module de crédit alimentaire gère les enveloppes mensuelles de tickets restaurant / avantages en nature pour les employés, utilisables en caisse POS.

### 5.2 Cycle de vie du crédit alimentaire

```
Brouillon  ──►  En cours  ──►  Clôturé / Terminé
  (draft)    (in_progress)    (close / done)
```

---

### 5.3 Accéder aux crédits alimentaires

**Accès** : `Ventes › Configuration › Crédit alimentaire`

---

### 5.4 Générer les crédits alimentaires du mois

**Accès** : Bouton **[Générer Crédits + Lignes]** dans la liste OU assistant dédié

#### Via l'assistant de génération

1. Ouvrir l'assistant **Générer Crédits Alimentaires**
2. Remplir :

| Champ | Description |
|---|---|
| **Jour** | Jour de début de la période |
| **Mois** | Mois concerné |
| **Année** | Année concernée |
| **Écraser l'existant** | Recréer si un crédit existe déjà pour cette période |
| **Sociétés** | Sociétés pour lesquelles générer les crédits |

3. Cliquer sur **[Générer]**
4. Un enregistrement `food.credit` est créé par société, avec une ligne par employé

---

### 5.5 Gérer un crédit alimentaire

#### Mettre en cours

- Ouvrir la fiche du crédit
- Cliquer sur **[Mettre en cours]** — Le crédit devient consommable en caisse POS

#### Consulter la consommation

Dans l'onglet **Employés**, pour chaque ligne :

| Colonne | Description |
|---|---|
| **Client** | Nom de l'employé |
| **Solde** | Montant restant disponible (calculé) |
| **Montant utilisé** | Consommation cumulée |

#### Bloquer temporairement

- Cliquer sur **[Bloquer]** — Suspend les paiements sans clôturer

#### Clôturer

- Cliquer sur **[Clôturer]** — Ferme définitivement la période

---

### 5.6 Générer les factures

1. Depuis la fiche du crédit en état **En cours** ou **Terminé**
2. Cliquer sur **[Générer les factures]**
3. Un avoir/facture comptable est créé pour chaque enveloppe consommée

---

### 5.7 Actions en masse depuis la liste

Dans la vue liste des crédits alimentaires :

| Bouton | Action |
|---|---|
| **[Générer Crédits + Lignes]** | Crée les crédits et les lignes employés en une seule action |
| **[Soumettre pour validation]** | Valide les crédits sélectionnés |
| **[Clôturer]** | Clôture les crédits sélectionnés |

> ⚠️ L'action **[Générer Crédits + Lignes]** demande une confirmation avant exécution.

---

### 5.8 Gestion des plafonds

**Accès** : Assistant **Mettre à jour plafonds** / **Importer plafonds**

- Permet de définir un plafond de consommation mensuelle par employé
- Import possible depuis un fichier Excel via l'assistant d'import de plafonds

---

## 6. Intégration SAGE X3 (`custom_api_sage_x3`)

### 6.1 Présentation

Ce module assure la synchronisation entre Odoo et l'ERP **SAGE X3** :
- Envoi des commandes d'achat vers SAGE X3
- Réception des livraisons depuis SAGE X3
- Envoi des écritures comptables

---

### 6.2 Envoi vers SAGE X3 depuis un bon de commande

Lors de la **confirmation** d'un bon de commande, l'envoi vers SAGE X3 est déclenché automatiquement.

Le statut de synchronisation est visible sur la fiche du bon de commande :

| Champ | Description |
|---|---|
| **Envoyé à SAGE X3** | Commande transmise |
| **Validé par SAGE X3** | Confirmation reçue de SAGE X3 |
| **Livraison reçue** | Livraison importée depuis SAGE X3 |
| **Date d'envoi** | Horodatage de la transmission |
| **Date de livraison** | Date de réception confirmée |
| **Message SAGE X3** | Réponse de l'API |

---

### 6.3 Envoi en masse des écritures comptables

**Accès** : `Comptabilité › Intégration SAGE X3 › Envoyer vers SAGE X3`  

> ⚠️ **Avertissement** : Cette action envoie en masse des données comptables vers SAGE X3.

**Étapes :**

1. Ouvrir l'assistant d'envoi
2. Vérifier les informations pré-remplies :

| Champ | Description |
|---|---|
| **Sociétés** | Sociétés concernées (lecture seule) |
| **Date du** | Date de début |
| **Date au** | Date de fin |
| **Avoirs** | Nombre d'avoirs à envoyer (lecture seule) |
| **Paiements** | Nombre de paiements à envoyer (lecture seule) |
| **Sessions POS** | Nombre de sessions POS à envoyer (lecture seule) |
| **Factures de vente** | Nombre de factures à envoyer (lecture seule) |

3. Cliquer sur **[Confirmer l'envoi]**

> ℹ️ Le bouton **[Confirmer l'envoi]** est masqué si tous les compteurs sont à 0.

---

### 6.4 Consulter les logs d'intégration

**Accès** : `Comptabilité › Intégration SAGE X3 › Logs d'import`

Affiche l'historique de toutes les opérations SAGE X3 avec :
- Statut (Succès / Avertissement / Erreur)
- Données de la requête envoyée
- Réponse reçue
- Horodatage

---

## 7. Achats (`custom_purchase`)

### 7.1 Import des prix fournisseurs

**Accès** : `Achats › Configuration › Import Prix Fournisseurs`

Permet de mettre à jour en masse les prix fournisseurs depuis un fichier Excel.

#### Format du fichier Excel requis

| Colonne | Description |
|---|---|
| `partner_id` | Identifiant du fournisseur |
| `product_tmpl_id` | Référence du produit |
| `company_id` | Identifiant de la société |
| `price` | Nouveau prix fournisseur |

#### Étapes

**Étape 1 — Charger le fichier**

1. Ouvrir l'assistant d'import
2. Renseigner la **Société**
3. Cliquer sur **[Charger le fichier]** et sélectionner le fichier Excel

**Étape 2 — Vérifier les résultats**

Dans l'onglet **Lignes chargées**, chaque ligne est colorée selon son statut :

| Couleur | Statut | Signification |
|---|---|---|
| Vert | `create` | Nouvelle entrée de prix |
| Orange | `update` | Mise à jour d'un prix existant |
| Rouge | `not_found` | Produit ou fournisseur non trouvé dans Odoo |

Les colonnes affichées :
- Fournisseur (Excel) / Fournisseur trouvé
- Code produit / Produit trouvé
- Société
- Nouveau prix / Prix existant
- Action à effectuer

**Étape 3 — Confirmer**

1. Vérifier les lignes en rouge (non trouvées) et corriger le fichier si nécessaire
2. Cliquer sur **[Confirmer l'import]** pour appliquer les prix

---

### 7.2 Réapprovisionnement fournisseur

**Accès** : `Achats › Réapprovisionnement › Assistant fournisseur`

Permet de sélectionner le fournisseur optimal pour chaque article à réapprovisionner.

**Étapes :**
1. Ouvrir l'assistant
2. Sélectionner les produits à réapprovisionner
3. Associer chaque produit à son fournisseur
4. Valider pour créer les bons de commande

---

### 7.3 Filtrage des produits dans les achats

Lors de la création d'un bon de commande, les produits sont **filtrés automatiquement** :
- Seuls les produits **actifs dans SAGE X3** (`actif_x3 = 1`) sont proposés
- Les produits au statut `D` (désactivé) pour la société courante sont exclus

---

## 8. Comptabilité (`custom_account`)

### 8.1 Budget analytique

**Accès** : `Comptabilité › Budgets › Budgets analytiques`

#### Créer un budget analytique

1. Ouvrir la fiche du budget analytique
2. Renseigner les axes analytiques et montants
3. La ventilation journalière est calculée automatiquement dans **Budget analytique journalier**

---

### 8.2 Suivi des dépenses

Le module enrichit les **écritures comptables** avec :
- **Mode de paiement** — visible sur la facture (lecture seule si non brouillon)
- Intégration avec les règles multi-société

---

## 9. Partenaires (`custom_partner`)

### 9.1 Fiche partenaire enrichie

La fiche partenaire standard est enrichie avec :
- **Carte de fidélité** — Lien vers la carte de fidélité du client
- **Crédit alimentaire** — Solde disponible (pour les employés)
- **Données SAGE X3** — Identifiant client/fournisseur SAGE X3

### 9.2 Activer la fidélité pour un client

1. Ouvrir la fiche partenaire
2. Dans l'onglet **Fidélité**, cocher **Est fidélisé**
3. Une carte de fidélité est automatiquement créée

---

## 10. Rapports et Analyses (`custom_reports`)

### 10.1 Accès aux rapports

**Accès principal** : `Gestion d'administration › Analyse et Rapports`

Les rapports sont organisés en 3 catégories :
- **Ventes et Clients**
- **Fournisseurs et Achats**
- **Stock et Inventaire**

---

### 10.2 Récapitulatif Caisses

**Accès** : `Analyse et Rapports › Ventes et Clients › Récapitulatif Caisses`

**Étapes :**

1. Renseigner :
   - **Date du** *(obligatoire)* — Début de période
   - **Date au** *(obligatoire)* — Fin de période
   - **Société** — Pré-remplie, non modifiable
   - **Configurations** — Sélectionner une ou plusieurs caisses (optionnel)
   - **Caissiers** — Filtrer par caissier (optionnel, se peuple selon les dates)

2. Cliquer sur **[Télécharger PDF]** pour le rapport PDF
3. Cliquer sur **[Télécharger Excel]** pour l'export Excel

---

### 10.3 Cadencier des ventes

**Accès** : `Analyse et Rapports › Ventes et Clients › Cadencier Ventes Articles`

**Étapes :**

1. Renseigner :
   - **Année** *(obligatoire)* — Année analysée
   - **Familles** — Familles de produits (optionnel)
   - **Société** — Pré-remplie

2. Cliquer sur **[Imprimer le rapport]** pour le PDF
3. Cliquer sur **[Exporter Excel]** pour l'export

---

### 10.4 État des stocks magasin

**Accès** : `Analyse et Rapports › Stock et Inventaire › Stock Magasin`

1. Vérifier la société pré-remplie
2. Cliquer sur **[Générer le rapport Excel]** (raccourci : **V**)

---

### 10.5 Autres rapports disponibles

| Rapport | Accès | Format |
|---|---|---|
| **Valorisation du stock** | Stock et Inventaire | PDF/Excel |
| **Statistiques de ventes** | Ventes et Clients | PDF/Excel |
| **Réceptions fournisseurs** | Fournisseurs et Achats | PDF |
| **Retours fournisseurs** | Fournisseurs et Achats | PDF |
| **Cumul inventaire** | Stock et Inventaire | PDF |
| **Ajustements de stock** | Stock et Inventaire | PDF |
| **Casses et pertes** | Stock et Inventaire | PDF |
| **Ventes journalières** | Ventes et Clients | PDF |
| **Catalogue produits** | Stock et Inventaire | PDF/Excel |
| **Retours consolidés** | Stock et Inventaire | PDF |
| **Bons de livraison** | Ventes et Clients | PDF |
| **Rapport produits stock** | Stock et Inventaire | PDF/Excel |

> ℹ️ Chaque rapport dispose d'un assistant avec des filtres (dates, société, catégories) adaptés à son contenu.

---

## 11. Rapport de Reliquats (`custom_reliquat_report`)

### 11.1 Présentation

Le rapport de reliquats mesure le **taux de satisfaction des commandes fournisseurs** : quantité commandée vs. quantité effectivement reçue.

---

### 11.2 Créer un rapport de reliquats

**Accès** : `Rapports › Reliquats › Créer un rapport`

**Étapes :**

1. Ouvrir l'assistant de génération
2. Renseigner :

| Champ | Description |
|---|---|
| **Type de période** | Journalier / Hebdomadaire / Mensuel / Trimestriel / Semestriel / Annuel |
| **Date du** | Date de début de la période |
| **Date au** | Date de fin de la période |

3. Cliquer sur **[Générer le rapport]**

---

### 11.3 Consulter un rapport généré

Le rapport affiche pour chaque référence :

| Indicateur | Description |
|---|---|
| **Total commandes** | Nombre de bons de commande |
| **Qté commandée** | Quantité totale commandée |
| **Qté reçue** | Quantité totale reçue |
| **Qté en attente** | Reliquat (commandé − reçu) |
| **Taux de satisfaction** | `(Qté reçue / Qté commandée) × 100` |

---

### 11.4 Génération automatique mensuelle

Un **cron automatique** génère chaque mois le rapport du mois précédent.

Aucune action manuelle requise pour la génération mensuelle.

---

## 12. Multi-Codes-Barres Produits (`custom_multi_barcode_for_products`)

### 12.1 Présentation

Ce module permet d'associer **plusieurs codes-barres** à un même produit. Le code-barres actif est synchronisé avec le champ standard d'Odoo.

---

### 12.2 Gérer les codes-barres d'un produit

**Accès** : `Inventaire › Produits › Produits` → Ouvrir un produit

1. Dans la fiche produit, aller dans l'onglet **Code-barres** (visible uniquement si le produit n'a pas de variantes)
2. La liste des codes-barres alternatifs s'affiche :

| Colonne | Description |
|---|---|
| **Code-barres** | Valeur du code-barres |
| **Actif** | Code-barres principal (synchronisé avec le champ standard) |

3. **Ajouter** un code-barres : cliquer sur **[Ajouter une ligne]**
4. **Activer** un code-barres : cocher la case **Actif** sur la ligne souhaitée
5. Cliquer sur **[Sauvegarder]**

> ℹ️ Un seul code-barres peut être **actif** à la fois. Activer un code-barres désactive automatiquement l'ancien.

> ⚠️ Les codes-barres doivent être **uniques** dans toute la base de données. Un code déjà utilisé sera rejeté.

---

### 12.3 Rechercher un produit par code-barres

Dans la recherche produit, les champs suivants sont indexés :
- Code article
- Référence interne
- Code-barres principal
- **Tous les codes-barres alternatifs**
- Nom du produit

---

### 12.4 Import en masse de codes-barres

**Accès** : Assistant d'import (depuis le menu Configuration)

**Étapes :**
1. Préparer un fichier Excel avec les colonnes : `product_code`, `barcode`
2. Charger le fichier dans l'assistant
3. Vérifier les correspondances produit
4. Confirmer l'import

---

### 12.5 Impression d'étiquettes multi-codes-barres

Depuis la liste ou la fiche produit :
1. Sélectionner le(s) produit(s)
2. Choisir **Action › Imprimer Étiquettes**
3. L'étiquette inclut tous les codes-barres actifs du produit

---

## 13. Suivi des Prix (`custom_price_change_tracker`)

### 13.1 Présentation

Ce module trace automatiquement toutes les modifications de prix produits et envoie une notification quotidienne.

---

### 13.2 Consulter l'historique des prix

**Accès** : `Produits › Historique des prix`

La liste affiche toutes les modifications de prix avec des indicateurs visuels :
- **Vert** — Hausse de prix
- **Rouge** — Baisse de prix

| Colonne | Description |
|---|---|
| **Date de modification** | Horodatage du changement |
| **Produit** | Produit concerné |
| **Ancien prix** | Prix avant modification |
| **Nouveau prix** | Prix après modification |
| **Différence** | Écart en valeur |
| **% de variation** | Variation en pourcentage |
| **Utilisateur** | Qui a modifié |
| **Notifié** | Notification envoyée (oui/non) |
| **État** | Brouillon / Notifié |

---

### 13.3 Filtres de recherche disponibles

| Filtre | Description |
|---|---|
| **Non notifiés** | Changements sans notification envoyée |
| **Notifiés** | Changements déjà notifiés |
| **Hausses de prix** | Variation positive uniquement |
| **Baisses de prix** | Variation négative uniquement |
| **Variations importantes** | Variation > 10 % |
| **Aujourd'hui** | Modifications du jour |
| **Hier** | Modifications d'hier |
| **Semaine passée** | 7 derniers jours |
| **Mois passé** | 30 derniers jours |

---

### 13.4 Actions sur un enregistrement

**Depuis la fiche d'un changement de prix :**

| Bouton | Action |
|---|---|
| **[Imprimer étiquette]** | Génère et imprime l'étiquette code-barres du produit (visible si non notifié) |
| **[Marquer comme notifié]** | Passe l'état à **Notifié** |
| **[Mettre en attente]** | Repasse en état **Brouillon** si déjà notifié |

---

### 13.5 Actions en masse (depuis la liste)

Sélectionner plusieurs enregistrements puis :
- **Action › Imprimer Étiquettes** — Impression en masse des étiquettes

---

### 13.6 Notification automatique quotidienne

Un **cron automatique** s'exécute chaque jour à **8h00** et envoie une notification récapitulant tous les changements de prix non notifiés.

Aucune action manuelle requise.

---

## 14. Tableau de Bord Administration (`dashboard_management_administration`)

### 14.1 Accès

**Accès** : `Gestion d'administration › Dashboard`

---

### 14.2 Dashboard principal

Le tableau de bord affiche en temps réel les **indicateurs clés** :

| Indicateur | Description |
|---|---|
| **Chiffre d'affaires** | CA ventes + POS sur la période |
| **Top 5 clients** | Clients générant le plus de CA |
| **Graphique ventes** | Évolution des ventes (Chart.js interactif) |
| **Achats** | Volume des commandes d'achat |
| **POS** | Transactions en caisse |

**Filtres disponibles** :
- Sélection de la période (date début / date fin)
- Filtre par société

---

### 14.3 Dashboard Gestion Admin (Actions POS)

**Accès** : `Gestion d'administration › Gestion Admin`

Affiche les **métriques POS en temps réel** :
- Sessions ouvertes
- Transactions en cours
- Alertes opérationnelles

---

## 15. Certification FNE (`fne_certification`)

### 15.1 Présentation

La certification FNE (Facture Normalisée Électronique) est la procédure de certification fiscale obligatoire des factures auprès de l'administration fiscale.

---

### 15.2 Certifier une facture

**Prérequis** : La facture doit être **validée** (état Comptabilisé).

**Étapes :**

1. Ouvrir la facture dans `Comptabilité › Clients › Factures`
2. Cliquer sur **[Certifier FNE]** (bouton d'action sur la facture)
3. L'assistant de certification s'ouvre avec les informations pré-remplies :

| Champ | Description |
|---|---|
| **Facture** | Référence de la facture (lecture seule) |
| **Client** | Partenaire facturé (lecture seule) |
| **Gabarit FNE** | Sélectionner le gabarit de certification (obligatoire) |
| **Mode de paiement FNE** | Mode de règlement pour la certification (obligatoire) |
| **Message commercial** | Texte libre à inclure sur la facture certifiée |
| **Pied de page** | Mention légale ou commerciale en bas de facture |

**Onglet Informations client** (lecture seule) :
- Nom, Email, Téléphone, NCC/TVA

4. Cliquer sur **[Certifier maintenant]**
5. La facture reçoit son numéro de certification FNE

---

### 15.3 Certifier un avoir (note de crédit)

**Prérequis** : L'avoir doit être basé sur une facture **déjà certifiée**.

**Étapes :**

1. Ouvrir l'avoir dans `Comptabilité › Clients › Avoirs`
2. Cliquer sur **[Certifier FNE Avoir]**
3. L'assistant affiche les lignes de l'avoir original :

| Colonne | Description |
|---|---|
| **À rembourser** | Cocher les lignes à inclure dans la certification |
| **Produit** | Produit concerné (lecture seule) |
| **Description** | Libellé (lecture seule) |
| **Quantité** | Quantité remboursée (lecture seule) |

4. Cocher uniquement les lignes à certifier
5. Cliquer sur **[Certifier FNE]**

> ⚠️ Seules les lignes **cochées** sont transmises à l'API FNE.

---

### 15.4 Imprimer une facture certifiée FNE

Depuis la facture certifiée :
1. Cliquer sur **[Imprimer]**
2. Sélectionner **Facture FNE** pour le format certifié

---

### 15.5 Configuration FNE

**Accès** : `Comptabilité › Configuration › Paramètres FNE`

Configurer :
- URL de l'API FNE
- Identifiants de connexion
- Gabarits de certification

---

## 16. Masquage de Menus (`hide_menu_user`)

### 16.1 Présentation

Ce module permet de **masquer des menus spécifiques** pour certains utilisateurs, indépendamment de leurs groupes de droits.

---

### 16.2 Restreindre un menu pour un utilisateur

**Accès** : `Paramètres › Technique › Interface Utilisateur › Éléments de menu`  
**Rôles** : Administrateur uniquement

**Étapes :**

1. Rechercher le menu à restreindre dans la liste
2. Ouvrir la fiche du menu
3. Aller dans l'onglet **Restreindre les utilisateurs**
4. Ajouter les utilisateurs **qui ne doivent PAS voir ce menu** dans la liste
5. Cliquer sur **[Sauvegarder]**

> ℹ️ Les utilisateurs listés dans cet onglet ne verront plus le menu dans leur interface, même s'ils appartiennent à un groupe qui y donne normalement accès.

---

### 16.3 Vérifier les restrictions d'un utilisateur

1. Aller dans `Paramètres › Utilisateurs et sociétés › Utilisateurs`
2. Ouvrir la fiche de l'utilisateur
3. La liste des menus restreints est visible dans l'onglet dédié

---

## Annexe A — Groupes d'accès et permissions

| Groupe | Module | Droits principaux |
|---|---|---|
| `Caissière` | custom_pos | Saisie ventes POS |
| `Superviseur` | custom_pos | Supervision, corrections, validations inventaire |
| `Assistant Magasin` | custom_pos | Ventes, stocks, réceptions |
| `Responsable Magasin` | custom_pos | Accès complet magasin |
| `Commercial` | custom_pos | Ventes et comptes (limité) |
| `Point Control` | custom_sales | Gestion des promotions |
| `Manager POS` | point_of_sale | Gestion complète POS |
| `DSI IT` | custom_pos | Accès technique complet |

---

## Annexe B — Raccourcis clavier POS

| Raccourci | Action |
|---|---|
| **Alt + C** | Ouvrir le tiroir-caisse manuellement |
| **V** | Générer le rapport stock magasin (dans l'assistant) |

---

## Annexe C — Formats des fichiers Excel d'import

### Import stock (`stock_excel_import_wizard`)
| Colonne | Type | Obligatoire |
|---|---|---|
| Code produit | Texte | Oui |
| Quantité | Nombre | Oui |
| Coût | Nombre | Non |

### Import prix fournisseurs (`custom_purchase`)
| Colonne | Type | Obligatoire |
|---|---|---|
| `partner_id` | Entier | Oui |
| `product_tmpl_id` | Entier/Texte | Oui |
| `company_id` | Entier | Oui |
| `price` | Nombre | Oui |

### Import codes-barres (`custom_multi_barcode_for_products`)
| Colonne | Type | Obligatoire |
|---|---|---|
| `product_code` | Texte | Oui |
| `barcode` | Texte | Oui |

### Import points fidélité (`custom_pos`)
Télécharger le gabarit depuis l'assistant — format défini dans le gabarit.

---

## Annexe D — Tâches automatiques (Crons)

| Tâche | Fréquence | Action |
|---|---|---|
| Garde-fou AVCO | Quotidien | Vérifie les écarts de coût AVCO > ±10 M FCFA |
| Notification des prix | Quotidien à 8h | Envoie un récapitulatif des changements de prix |
| Rapport reliquats | Mensuel | Génère automatiquement le rapport du mois précédent |
| Import livraisons SAGE X3 | Planifié | Importe les livraisons depuis SAGE X3 |
| Génération crédits alimentaires | Mensuel | Crée les enveloppes mensuelles par société |

---

*Manuel d'utilisation SANGEL — Odoo 19 — Mai 2026*
