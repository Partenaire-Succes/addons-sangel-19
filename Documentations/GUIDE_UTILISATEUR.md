# Guide Utilisateur — Suite SANGEL Odoo 19
### Organisé par rôle métier

**Version** : 19.0  
**Date** : Mai 2026  
**Public** : Utilisateurs métier en prise en main ou en formation

---

## Comment utiliser ce guide ?

Trouvez votre rôle dans la table des matières et suivez les scénarios du quotidien.  
Chaque scénario est une suite d'étapes concrètes, dans l'ordre où vous les ferez à l'écran.

---

## Table des matières

- [Rôle 1 — Caissière](#rôle-1--caissière)
- [Rôle 2 — Superviseur de Caisse](#rôle-2--superviseur-de-caisse)
- [Rôle 3 — Assistant Magasin](#rôle-3--assistant-magasin)
- [Rôle 4 — Responsable Magasin](#rôle-4--responsable-magasin)
- [Rôle 5 — Commercial](#rôle-5--commercial)
- [Rôle 6 — Comptable](#rôle-6--comptable)
- [Rôle 7 — Administrateur / DSI IT](#rôle-7--administrateur--dsi-it)

---

---

# Rôle 1 — Caissière

> **Votre journée en bref** : Vous encaissez les clients, gérez votre session de caisse et imprimez les tickets. Ce guide couvre tout ce dont vous avez besoin au quotidien.

---

## Scénario 1.1 — Ouvrir sa session de caisse

1. Connectez-vous à Odoo avec votre identifiant
2. Allez dans `Point de Vente`
3. Cliquez sur **[Ouvrir]** en face de votre caisse
4. Saisissez le **montant du fond de caisse** (espèces en caisse au départ)
5. Cliquez sur **[Ouvrir la session]**
6. La caisse est prête — l'écran de vente s'affiche

---

## Scénario 1.2 — Enregistrer une vente

1. Sur l'écran de vente, **scannez le code-barres** du produit ou recherchez-le par nom
   - Le système reconnaît tous les codes-barres du produit (principaux et secondaires)
2. La ligne apparaît dans la commande avec le prix et la quantité
3. Répétez pour chaque article
4. Cliquez sur **[Paiement]**

---

## Scénario 1.3 — Encaisser un client (paiement simple)

Suite du scénario 1.2 :

1. Sur l'écran de paiement, sélectionnez le **mode de paiement** (Espèces, Carte, Mobile Money…)
2. Saisissez le **montant reçu**
3. Le **rendu monnaie** se calcule automatiquement
4. Cliquez sur **[Valider]**
5. Le ticket s'imprime automatiquement

---

## Scénario 1.4 — Encaisser en devise étrangère

1. Sur l'écran de paiement, sélectionnez le mode de paiement en devise étrangère (ex : Euros, Dollars)
2. Une **popup de conversion** s'affiche automatiquement avec :
   - Le montant en devise étrangère
   - Le taux de change en vigueur
   - L'équivalent en FCFA
3. Vérifiez le montant converti
4. Cliquez sur **[Confirmer]** pour valider le paiement

---

## Scénario 1.5 — Utiliser le crédit alimentaire d'un employé

1. Sur l'écran de vente, **sélectionnez le client** (employé) avant de valider
2. Sur l'écran de paiement, sélectionnez **Crédit alimentaire** comme mode de paiement
3. Le solde disponible s'affiche automatiquement
4. Saisissez le montant à débiter (inférieur ou égal au solde)
5. Cliquez sur **[Valider]**

> ⚠️ Si le client n'a pas de solde crédit alimentaire, ce mode de paiement sera refusé.

---

## Scénario 1.6 — Paiement mixte (espèces + carte)

1. Sur l'écran de paiement, sélectionnez **Espèces** et saisissez le montant partiel
2. Cliquez sur **[+]** pour ajouter un second mode de paiement
3. Sélectionnez **Carte bancaire** et saisissez le reste
4. Vérifiez que le total equals le montant de la commande
5. Cliquez sur **[Valider]**

---

## Scénario 1.7 — Appliquer une remise sur un article

> ⚠️ Les remises nécessitent une **validation manager** avec code d'accès.

1. Dans la commande, sélectionnez la ligne à modifier
2. Cliquez sur **[Remise]** et saisissez le pourcentage
3. Une fenêtre demande le **code d'accès manager**
4. Le superviseur saisit son code
5. La remise est appliquée sur la ligne

---

## Scénario 1.8 — Rembourser un client (avoir)

1. Sur l'écran principal POS, cliquez sur **[Tickets]**
2. Recherchez le ticket d'origine par numéro ou date
3. Sélectionnez le ticket et cliquez sur **[Rembourser]**
4. Sélectionnez les articles à rembourser et les quantités
5. Cliquez sur **[Rembourser]** pour confirmer
6. Le montant est restitué selon le mode de paiement choisi

---

## Scénario 1.9 — Ouvrir le tiroir-caisse manuellement

- Appuyez sur **Alt + C** sur le clavier
- Le tiroir s'ouvre sans créer de transaction

---

## Scénario 1.10 — Clôturer sa session de caisse

1. Cliquez sur le **menu hamburger** (≡) en haut à droite
2. Cliquez sur **[Fermer]**
3. Comptez vos espèces et saisissez le **total espèces en caisse**
4. Le système affiche l'écart éventuel avec le théorique
5. Cliquez sur **[Clôturer la session]**
6. Le rapport de clôture est généré automatiquement

---

---

# Rôle 2 — Superviseur de Caisse

> **Votre journée en bref** : Vous validez les opérations sensibles, gérez les incidents de caisse, contrôlez les sessions et produisez les rapports de caisse.

---

## Scénario 2.1 — Valider une opération sensible (code manager)

Quand une caissière déclenche une action nécessitant une validation :

1. Une fenêtre **Code d'accès manager** s'affiche sur l'écran de la caissière
2. Vous saisissez votre **code d'accès personnel**
3. L'opération (remise, modification de prix, etc.) est débloquée

> ℹ️ Vos codes d'accès sont configurés dans `Point de Vente › Configuration › Codes manager`.

---

## Scénario 2.2 — Corriger un paiement sur une commande déjà imprimée

1. Allez dans `Point de Vente › Commandes`
2. Recherchez la commande concernée
3. Ouvrez-la et cliquez sur **[Modifier le paiement]**
4. Corrigez le mode ou le montant de paiement
5. Sauvegardez

> ℹ️ Cette action est autorisée même sur les commandes déjà imprimées grâce à la personnalisation SANGEL.

---

## Scénario 2.3 — Consulter le rapport des validations

Ce rapport liste toutes les opérations que vous avez validées (remises accordées, prix modifiés…).

1. Allez dans `Point de Vente › Rapport des validations`
2. Renseignez :
   - **Date du** et **Date au**
   - **Configurations** (caisses à analyser, optionnel)
3. Cliquez sur **[Télécharger le rapport]**

---

## Scénario 2.4 — Produire le récapitulatif des caisses

1. Allez dans `Gestion d'administration › Analyse et Rapports › Récapitulatif Caisses`
2. Renseignez :
   - **Date du** / **Date au**
   - **Configurations** (toutes les caisses ou une seule)
   - **Caissiers** (optionnel, pour filtrer par caissière)
3. Cliquez sur **[Télécharger PDF]** ou **[Télécharger Excel]**

---

## Scénario 2.5 — Analyser les paiements par mode

1. Allez dans `Point de Vente › Rapport de mode paiement`
2. Renseignez la période
3. Filtrez par mode de paiement si nécessaire
4. Cliquez sur **[Télécharger le rapport PDF]**

---

## Scénario 2.6 — Valider un inventaire physique

Après que l'équipe a saisi toutes les quantités physiques :

1. Ouvrez l'inventaire en état **En cours**
2. Vérifiez les écarts (colonnes colorées : vert = surplus, rouge = manquant)
3. Si tout est correct, cliquez sur **[Valider l'inventaire]**
4. Le stock est ajusté automatiquement

> ⚠️ Cette action est **irréversible**. Vérifiez soigneusement avant de valider.

---

## Scénario 2.7 — Imprimer la fiche de comptage pour l'équipe

Avant de commencer un inventaire, imprimez les fiches vierges :

1. Ouvrez l'inventaire en état **Brouillon**
2. Cliquez sur **[Imprimer fiche de comptage]**
3. Distribuez les fiches à l'équipe pour le comptage physique

---

---

# Rôle 3 — Assistant Magasin

> **Votre journée en bref** : Vous gérez les réceptions de marchandises, les retours fournisseurs, participez aux inventaires et assurez la gestion quotidienne des stocks.

---

## Scénario 3.1 — Réceptionner une livraison sans bon de commande

1. Allez dans `Inventaire › Opérations › Réception directe`
2. Remplissez l'en-tête :
   - **Fournisseur** — Qui livre ?
   - **Date prévue** — Aujourd'hui (par défaut)
   - **Emplacement de destination** — Où stocker ?
   - **Référence SAGE** — Numéro du document SAGE X3 (si disponible)
3. Ajoutez les lignes :
   - **Produit** → **Quantité** → **Prix unitaire** (si différent du coût habituel, saisissez le **Nouveau prix**)
4. Vérifiez le **Montant total** calculé automatiquement
5. Cliquez sur **[Valider la réception]** puis confirmez

---

## Scénario 3.2 — Réceptionner une livraison sur bon de commande

1. Allez dans `Achats › Commandes › Bons de commande`
2. Ouvrez le bon de commande correspondant à la livraison
3. Cliquez sur **[Réceptionner]**
4. Vérifiez et ajustez les quantités reçues si nécessaire
5. Cliquez sur **[Valider]**

---

## Scénario 3.3 — Créer un retour fournisseur

1. Allez dans `Inventaire › Opérations › Nouveau retour fournisseur`
2. Remplissez :
   - **Fournisseur** — Obligatoire
   - **Date prévue**
   - **Référence externe** — Numéro du fournisseur
   - **Générer avoir** — Cocher si vous souhaitez un avoir comptable automatique
3. Ajoutez les produits à retourner avec leurs quantités
4. Vérifiez le **stock disponible** pour chaque produit avant de saisir la quantité
5. Cliquez sur **[Créer le bon de retour]** et confirmez

---

## Scénario 3.4 — Participer à un inventaire physique

Votre superviseur a créé et lancé l'inventaire. Votre rôle est de saisir les quantités comptées.

1. Ouvrez l'inventaire en état **En cours** depuis `Inventaire › Ajustements › Inventaire physique`
2. Dans l'onglet **Lignes d'inventaire physique**, pour chaque produit :
   - Comptez physiquement les articles dans le rayon
   - Saisissez la quantité dans la colonne **Qté physique**
   - Notez votre nom dans **Vérifié par**
3. L'écart (différence avec le stock théorique) se calcule automatiquement
4. Signalez toute anomalie au superviseur avant validation

---

## Scénario 3.5 — Rechercher un produit par code-barres

Dans la recherche produit (barre de recherche en haut) :
- Scannez ou tapez n'importe quel code-barres associé au produit
- Le système recherche dans **tous** les codes-barres (principaux et secondaires)

---

## Scénario 3.6 — Consulter les retours fournisseurs passés

1. Allez dans `Inventaire › Opérations › Historique retours fournisseur`
2. Utilisez les filtres pour rechercher par fournisseur, date ou produit

---

## Scénario 3.7 — Importer du stock depuis un fichier Excel

1. Allez dans `Inventaire › Ajustements › Import Stock Excel`
2. Sélectionnez la **Société**, l'**Entrepôt** et l'**Emplacement**
3. Cliquez sur **[Charger Produits]** et sélectionnez votre fichier Excel
4. Vérifiez les lignes chargées (produits trouvés / non trouvés)
5. Cliquez sur **[Confirmer]** pour appliquer

---

---

# Rôle 4 — Responsable Magasin

> **Votre journée en bref** : Vous supervisez l'ensemble des opérations du magasin — stocks, ventes, promotions, reporting — et prenez les décisions de gestion.

---

## Scénario 4.1 — Créer et lancer une promotion

1. Allez dans `Point de Vente › Promotions Sangel`
2. Cliquez sur **[Nouveau]**
3. Donnez un nom (ex : *PROMO-MAI-2026*)
4. Définissez les **dates de validité** (début et fin)
5. Sélectionnez les **sociétés** concernées
6. Ajoutez les produits en promotion dans les lignes :
   - Saisissez soit la **Remise %**, soit le **Prix Promo HT**, soit le **Prix Promo TTC**
   - Les autres valeurs se calculent automatiquement
7. Sauvegardez

> ℹ️ La promotion s'applique automatiquement en caisse POS pour les produits concernés.

---

## Scénario 4.2 — Analyser les ventes du jour

1. Allez dans `Gestion d'administration › Dashboard`
2. Le tableau de bord affiche :
   - Le **chiffre d'affaires** du jour
   - Le **top 5 des clients**
   - L'évolution des ventes en graphique
3. Ajustez la période avec les filtres de date si nécessaire

---

## Scénario 4.3 — Générer le rapport des ventes journalières

1. Allez dans `Analyse et Rapports › Ventes et Clients › Ventes journalières`
2. Sélectionnez la date
3. Cliquez sur **[Imprimer le rapport]**

---

## Scénario 4.4 — Contrôler le stock disponible

1. Allez dans `Analyse et Rapports › Stock et Inventaire › Stock Magasin`
2. Vérifiez la société pré-remplie
3. Cliquez sur **[Générer le rapport Excel]** (ou appuyez sur **V**)
4. Ouvrez le fichier Excel généré

---

## Scénario 4.5 — Organiser un inventaire physique

**Étape 1 — Créer l'inventaire**
1. Allez dans `Inventaire › Ajustements › Inventaire physique`
2. Cliquez sur **[Nouveau]**
3. Renseignez : Mode, Catégorie de code, Codes inventaire, Équipe, Date
4. Cliquez sur **[Générer les articles]** pour peupler les lignes
5. Sauvegardez

**Étape 2 — Préparer le terrain**
1. Cliquez sur **[Imprimer fiche de comptage]** — Distribuez aux équipes
2. Cliquez sur **[Soumettre pour validation]** — L'inventaire est en cours

**Étape 3 — Suivre la saisie**
1. Ouvrez l'inventaire en cours
2. Vérifiez que les lignes sont renseignées par l'équipe
3. Cliquez sur **[Actualiser Stock et Prix]** si nécessaire

**Étape 4 — Valider (ou déléguer au superviseur)**
1. Vérifiez les écarts
2. Cliquez sur **[Valider l'inventaire]**

---

## Scénario 4.6 — Gérer les reliquats fournisseurs

1. Allez dans `Rapports › Reliquats › Créer un rapport`
2. Sélectionnez la **période** et les **dates**
3. Cliquez sur **[Générer le rapport]**
4. Analysez le **taux de satisfaction** par fournisseur :
   - 100 % = toutes les commandes livrées
   - < 100 % = reliquat en attente

---

## Scénario 4.7 — Suivre les changements de prix produits

1. Allez dans `Produits › Historique des prix`
2. Utilisez les filtres :
   - **Hausses de prix** — Produits dont le prix a augmenté
   - **Baisses de prix** — Produits dont le prix a baissé
   - **Variations importantes** — Variations > 10 %
   - **Aujourd'hui** / **Semaine passée**

Pour chaque changement, vous pouvez :
- **[Imprimer étiquette]** — Réimprimer l'étiquette avec le nouveau prix
- **[Marquer comme notifié]** — Confirmer que l'équipe a été informée

---

## Scénario 4.8 — Créer un bon de commande fournisseur

1. Allez dans `Achats › Commandes › Bons de commande`
2. Cliquez sur **[Nouveau]**
3. Sélectionnez le **fournisseur**
4. Ajoutez les produits (filtrés automatiquement selon le statut SAGE X3)
5. Vérifiez les prix et quantités
6. Cliquez sur **[Confirmer la commande]**

> ℹ️ La commande est automatiquement transmise à **SAGE X3** après confirmation.

---

## Scénario 4.9 — Gérer les codes-barres d'un produit

1. Allez dans `Inventaire › Produits › Produits`
2. Ouvrez la fiche du produit
3. Onglet **Code-barres** :
   - Cliquez sur **[Ajouter une ligne]** pour ajouter un nouveau code-barres
   - Cochez **Actif** sur le code-barres principal
4. Sauvegardez

---

---

# Rôle 5 — Commercial

> **Votre journée en bref** : Vous créez et suivez les devis et commandes clients, gérez les promotions et consultez les performances commerciales.

---

## Scénario 5.1 — Créer un devis client

1. Allez dans `Ventes › Commandes › Devis`
2. Cliquez sur **[Nouveau]**
3. Sélectionnez le **Client**
4. Ajoutez les produits avec les quantités
5. Vérifiez si une **promotion** s'applique automatiquement sur les produits
6. Sauvegardez ou cliquez sur **[Envoyer par email]**

---

## Scénario 5.2 — Confirmer une commande

1. Ouvrez le devis depuis `Ventes › Commandes › Devis`
2. Vérifiez tous les détails
3. Cliquez sur **[Confirmer]**
4. La commande est créée — statut **En cours**

---

## Scénario 5.3 — Consulter les promotions actives

1. Allez dans `Point de Vente › Promotions Sangel`
2. Cliquez sur le filtre **Promotions actives**
3. Vous voyez toutes les promotions en cours avec :
   - Les produits concernés
   - Les remises accordées
   - Les dates de validité

---

## Scénario 5.4 — Analyser les ventes par article (cadencier)

1. Allez dans `Analyse et Rapports › Ventes et Clients › Cadencier Ventes Articles`
2. Renseignez :
   - **Année** — L'année à analyser
   - **Familles** — Catégories de produits (optionnel)
3. Cliquez sur **[Exporter Excel]** pour analyse détaillée

---

## Scénario 5.5 — Vérifier le stock d'un produit avant une commande

Sur la fiche d'un produit ou dans le devis :
- La colonne **Stock disponible** est visible dans les lignes de promotion
- Pour un contrôle précis : `Inventaire › Produits › Produits` → fiche produit → onglet **Stock en main**

---

---

# Rôle 6 — Comptable

> **Votre journée en bref** : Vous gérez la certification des factures, les intégrations comptables avec SAGE X3, les budgets et les avantages alimentaires.

---

## Scénario 6.1 — Certifier une facture FNE

1. Ouvrez la facture dans `Comptabilité › Clients › Factures`
   - La facture doit être en état **Comptabilisé** (validée)
2. Cliquez sur **[Certifier FNE]**
3. Dans l'assistant :
   - Sélectionnez le **Gabarit FNE** *(obligatoire)*
   - Sélectionnez le **Mode de paiement FNE** *(obligatoire)*
   - Ajoutez un **Message commercial** si souhaité
4. Vérifiez les données client dans l'onglet **Informations client**
5. Cliquez sur **[Certifier maintenant]**
6. La facture reçoit son numéro FNE

---

## Scénario 6.2 — Certifier un avoir FNE

1. Ouvrez l'avoir dans `Comptabilité › Clients › Avoirs`
2. Cliquez sur **[Certifier FNE Avoir]**
3. Dans l'assistant, **cochez les lignes** à inclure dans la certification
   - Décochez les lignes non concernées
4. Cliquez sur **[Certifier FNE]**

> ⚠️ Seules les lignes cochées seront transmises à l'administration fiscale.

---

## Scénario 6.3 — Imprimer une facture au format FNE

1. Ouvrez la facture certifiée
2. Cliquez sur **[Imprimer]**
3. Choisissez **Facture FNE** dans la liste des formats disponibles

---

## Scénario 6.4 — Envoyer les écritures comptables vers SAGE X3

> ⚠️ Cette action envoie des données en masse vers SAGE X3. Effectuez-la avec soin.

1. Allez dans `Comptabilité › Intégration SAGE X3 › Envoyer vers SAGE X3`
2. Vérifiez les informations pré-remplies :
   - Sociétés concernées
   - Période (Date du / Date au)
   - Compteurs : Avoirs, Paiements, Sessions POS, Factures
3. Si tout est correct, cliquez sur **[Confirmer l'envoi]**

---

## Scénario 6.5 — Consulter les logs SAGE X3

1. Allez dans `Comptabilité › Intégration SAGE X3 › Logs d'import`
2. Filtrez par statut :
   - **Succès** — Opérations réussies
   - **Avertissement** — À vérifier
   - **Erreur** — À corriger et relancer
3. Cliquez sur un log pour voir le détail de la requête et de la réponse

---

## Scénario 6.6 — Générer les crédits alimentaires du mois

1. Allez dans `Ventes › Configuration › Crédit alimentaire`
2. Cliquez sur **[Générer Crédits + Lignes]** dans la liste
3. Confirmez l'action
4. Un crédit est créé par société avec une ligne par employé

**OU via l'assistant :**
1. Cliquez sur **[Générer Crédits Alimentaires]**
2. Renseignez : Jour, Mois, Année, Sociétés
3. Cochez **Écraser l'existant** si vous régénérez le mois
4. Cliquez sur **[Générer]**

---

## Scénario 6.7 — Activer les crédits alimentaires

Après génération, les crédits sont en **Brouillon** et non utilisables en caisse.

Pour les activer :
1. Ouvrez la liste des crédits alimentaires
2. Sélectionnez les crédits du mois
3. Cliquez sur **[Soumettre pour validation]** → Statut **En cours**
4. Les employés peuvent maintenant utiliser leur crédit en caisse

---

## Scénario 6.8 — Facturer les crédits alimentaires consommés

En fin de mois :
1. Ouvrez chaque crédit alimentaire en état **En cours** ou **Terminé**
2. Cliquez sur **[Générer les factures]**
3. Les factures comptables sont créées automatiquement

---

## Scénario 6.9 — Mettre à jour les plafonds de crédit alimentaire

1. Ouvrez l'assistant **Mettre à jour plafonds** depuis le menu crédit alimentaire
2. Ajustez les plafonds par employé
3. Pour un import en masse, utilisez **[Importer plafonds]** avec un fichier Excel

---

## Scénario 6.10 — Suivre les budgets analytiques

1. Allez dans `Comptabilité › Budgets › Budgets analytiques`
2. Consultez la répartition par axe analytique
3. La ventilation journalière est disponible dans **Budget analytique journalier**

---

---

# Rôle 7 — Administrateur / DSI IT

> **Votre périmètre** : Configuration du système, gestion des droits, paramétrages techniques, imports de données et supervision de l'intégration SAGE X3.

---

## Scénario 7.1 — Configurer les caisses POS

1. Allez dans `Point de Vente › Configuration › Point de Vente`
2. Ouvrez la configuration de la caisse
3. Paramètres personnalisés SANGEL :
   - **Code d'accès pour rupture de stock** — Code à saisir en cas de vente sans stock
   - **Boutons de remise rapide** — Définissez des pourcentages prédéfinis (ex : 5%, 10%, 15%)
   - **Informations ticket de clôture** — Numéro de dépôt, numéro de poste

---

## Scénario 7.2 — Gérer les codes d'accès manager POS

1. Allez dans `Point de Vente › Configuration › Codes manager`
2. Créez un code par superviseur
3. Associez chaque code à l'utilisateur concerné

---

## Scénario 7.3 — Importer des points de fidélité en masse

1. Allez dans `Point de Vente › Import Excel Points Fidélité`
2. Cliquez sur **[Télécharger le gabarit]** pour obtenir le format Excel
3. Remplissez le fichier
4. Chargez le fichier et vérifiez les résultats
5. Cliquez sur **[Confirmer la mise à jour]**

---

## Scénario 7.4 — Importer des codes-barres en masse

1. Préparez un fichier Excel avec les colonnes `product_code` et `barcode`
2. Allez dans l'assistant d'import codes-barres
3. Chargez le fichier, vérifiez les correspondances
4. Confirmez l'import

---

## Scénario 7.5 — Importer les prix fournisseurs

1. Allez dans `Achats › Configuration › Import Prix Fournisseurs`
2. Chargez le fichier Excel (colonnes : `partner_id`, `product_tmpl_id`, `company_id`, `price`)
3. Vérifiez les couleurs :
   - **Vert** → Nouveau prix à créer
   - **Orange** → Prix existant à mettre à jour
   - **Rouge** → Produit ou fournisseur non trouvé (à corriger)
4. Corrigez les erreurs et rechargez, puis confirmez

---

## Scénario 7.6 — Masquer un menu pour un utilisateur

1. Allez dans `Paramètres › Technique › Interface Utilisateur › Éléments de menu`
2. Recherchez et ouvrez le menu à restreindre
3. Onglet **Restreindre les utilisateurs** → ajoutez l'utilisateur
4. Sauvegardez

> ℹ️ L'utilisateur ne verra plus ce menu même s'il a les droits du groupe associé.

---

## Scénario 7.7 — Configurer SAGE X3

1. Allez dans `Paramètres › Technique › Paramètres système`
2. Mettez à jour les paramètres :

| Clé | Valeur |
|---|---|
| `sage_x3.base_url` | URL de l'API SAGE X3 |
| `sage_x3.username` | Identifiant |
| `sage_x3.password` | Mot de passe |

---

## Scénario 7.8 — Configurer la certification FNE

1. Allez dans `Comptabilité › Configuration › Paramètres FNE`
2. Renseignez l'URL de l'API FNE et les identifiants
3. Configurez les gabarits de certification disponibles

---

## Scénario 7.9 — Vérifier les tâches automatiques (crons)

1. Allez dans `Paramètres › Technique › Automatisation › Actions planifiées`
2. Vérifiez que ces crons sont actifs :

| Tâche | Fréquence attendue |
|---|---|
| Garde-fou AVCO | Quotidien |
| Notification des prix | Quotidien à 8h |
| Rapport reliquats | Mensuel |
| Import livraisons SAGE X3 | Planifié (selon accord) |
| Génération crédits alimentaires | Mensuel |

---

## Scénario 7.10 — Gérer les familles de fidélité

1. Allez dans `Configuration › Fidélité › Familles`
2. Ouvrez ou créez une famille
3. Renseignez :
   - **Points gagnés** — Nombre de points par palier
   - **Seuil de montant** — Montant d'achat requis (en FCFA)
   - **Catégories de produits** — Produits éligibles

---

## Scénario 7.11 — Surveiller les logs SAGE X3

1. Allez dans `Comptabilité › Intégration SAGE X3 › Logs d'import`
2. Filtrez sur **Erreur** pour traiter les incidents
3. Pour chaque erreur, consultez :
   - Le message d'erreur retourné par SAGE X3
   - Les données de la requête envoyée
4. Corrigez la donnée dans Odoo et relancez l'opération

---

---

## Résumé des accès par rôle

| Fonctionnalité | Caissière | Superviseur | Ass. Magasin | Resp. Magasin | Commercial | Comptable | Admin |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Vente en caisse POS | ✅ | ✅ | ✅ | ✅ | — | — | — |
| Remise avec code manager | — | ✅ | — | ✅ | — | — | — |
| Clôture de session | ✅ | ✅ | — | ✅ | — | — | — |
| Rapport de caisse | — | ✅ | — | ✅ | — | — | ✅ |
| Réception marchandise | — | — | ✅ | ✅ | — | — | — |
| Retour fournisseur | — | ✅ | ✅ | ✅ | — | — | — |
| Inventaire (saisie) | — | ✅ | ✅ | ✅ | — | — | — |
| Inventaire (validation) | — | ✅ | — | ✅ | — | — | ✅ |
| Promotions | — | — | — | ✅ | ✅ | — | ✅ |
| Commandes fournisseur | — | — | ✅ | ✅ | — | — | — |
| Certification FNE | — | — | — | — | — | ✅ | ✅ |
| Envoi SAGE X3 | — | — | — | — | — | ✅ | ✅ |
| Crédit alimentaire | — | — | — | ✅ | — | ✅ | ✅ |
| Historique des prix | — | — | — | ✅ | ✅ | — | ✅ |
| Configuration système | — | — | — | — | — | — | ✅ |
| Masquage de menus | — | — | — | — | — | — | ✅ |

---

*Guide Utilisateur SANGEL — Odoo 19 — Mai 2026*
