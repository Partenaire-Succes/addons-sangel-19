# Module `custom_stock` — Guide utilisateur (Odoo)

Ce module ajoute des écrans et automatisations autour de l’**Inventaire** : codes d’inventaire, classification (rayon/famille), inventaire physique journalier (comptage + validation + impressions), transferts inter-magasins, et aide à la gestion des fournisseurs / règles de réapprovisionnement.

> Public visé : utilisateurs métier (magasiniers, chefs d’équipe, responsables stock, responsables produits).  
> Objectif : vous dire **où cliquer**, **quoi remplir**, et **quoi vérifier**.

---

## 1) Accès rapides (où cliquer)

### A. Configuration des codes et classifications

- **Inventaire → Configuration → Code inventaire → Code Catégorie**
- **Inventaire → Configuration → Code inventaire → Code**
- **Inventaire → Configuration → Categorie inventaire → Famille Categ** (catégories produits avec un *Code*)
- **Inventaire → Configuration → Categorie inventaire → Famille**
- **Inventaire → Configuration → Categorie inventaire → Sous Famille**
- **Inventaire → Configuration → Categorie inventaire → Rayon**
- **Inventaire → Configuration → Categorie inventaire → Sous Rayon**
- **Inventaire → Configuration → Categorie inventaire → Niveau 6 / Niveau 7 / Statut article / Type article** (référentiels “Sage X3”)

### B. Équipe d’inventaire

- **Inventaire → Configuration → Equipe Inventaire Journalier**

### C. Inventaire physique journalier (comptage)

- **Inventaire → Opérations → Ajustements d’inventaire → Inventaire Physique Journalier**

### D. Transferts inter-magasins

- **Inventaire → Opérations → Transferts → Transfert Inter Magasin**

### E. Réapprovisionnement / fournisseurs

- **Inventaire → Configuration → Règles de réapprovisionnement** : bouton **Mettre à jour les fournisseurs**
- **Achats → Produits → Produits → (ouvrir un produit) → onglet Achat → Fournisseurs** : bascule **Fournisseur principal**

---

## 2) Rôles & règles importantes (avant de commencer)

### Création de produits (restriction)

- Si vous n’êtes pas **Administrateur Produits**, la création manuelle d’un produit peut être bloquée (message indiquant que seuls les administrateurs produits peuvent créer).

### Validation d’inventaire (restriction)

- Le bouton **“Valider l’inventaire”** peut être visible uniquement pour certains profils (ex. “shop/point de vente”).

### Suppression d’un inventaire

- Un inventaire physique ne peut être supprimé que lorsqu’il est en **Brouillon/Comptage**.

---

## 3) Configurer les référentiels (codes / familles / rayons)

### 3.1 Code Catégorie & Code Inventaire

**But** : filtrer/organiser les produits pour l’inventaire physique.

1. Ouvrir **Inventaire → Configuration → Code inventaire → Code Catégorie**
2. Créer les catégories (ex. “Epicerie”, “Frais”, “Non alimentaire”…)
3. Aller ensuite sur **Inventaire → Configuration → Code inventaire → Code**
4. Créer les codes et **rattacher chaque Code à une Catégorie**

**À vérifier** : quand vous sélectionnez une *Catégorie* dans l’inventaire physique, la liste des *Codes* proposés doit correspondre.

### 3.2 Familles / Sous-familles

- **Famille** : référentiel simple (Nom + Code)
- **Sous Famille** : Nom + Code + rattachement à une Famille (ou à la “Famille” via catégorie produit selon votre paramétrage)

Astuce : gardez des codes **courts et stables** (éviter de les changer en cours d’année).

### 3.3 Rayons / Sous-rayons

Même logique que Famille/Sous-famille :

- **Rayon** : Nom + Code
- **Sous Rayon** : Nom + Code + rattachement à un Rayon

### 3.4 Référentiels “Sage X3” (Niveau 6 / Niveau 7 / etc.)

Dans **Categorie inventaire**, vous avez des menus pour :

- **Niveau 6** (catégorie de gestion)
- **Niveau 7** (famille article X3)
- **Type article**
- **Statut article**

Ils servent à compléter la fiche produit (onglet “Sage X3”).

---

## 4) Compléter une fiche produit (codes + classification + packs + X3)

Ouvrir un produit : **Inventaire → Produits → Produits** (ou via Achats/Ventes).

### 4.1 Code Inventaire + classification “en râteau”

Dans la fiche produit, vous trouverez :

- **Code Inventaire**
- **Système de classification en râteau** : *Rayon*, *Sous Rayon*, *Famille*, *Sous Famille*

Conseil : définissez ces champs sur tous les produits “stockables” pour faciliter les inventaires et les analyses.

### 4.2 Articles & remises

Vous trouverez une page **“Articles & remises”** :

- Options de remise (ex. *Remise sur ligne*)
- Paramètres de taxe AIRSI (si utilisé)
- **Décomposition d’articles (packs/cartons)**

### 4.3 Packs / cartons : fonctionnement attendu

Si un produit est un **Article pack (carton)** :

- Vous liez un **Sous-article (unité)** et une **Qté par carton**.
- Le système calcule des équivalences (stock “cartons équiv.” / stock unités).

**Effets attendus sur le stock** (simplifié) :

- **Réception de cartons** : peut augmenter automatiquement le stock des **unités**.
- **Sortie/livraison d’unités** : peut “consommer” des cartons quand un multiple complet est atteint.
- **Vente/livraison de cartons** : peut décrémenter les unités correspondantes (cohérence pack/unité).

> Si vous constatez un écart, notez le produit, la date et l’opération (réception/livraison) puis remontez au responsable stock : ce mécanisme automatise la cohérence pack/unité.

### 4.4 Onglet “Sage X3”

Vous trouverez :

- Catégorie/Famille/Type/Statut article (référentiels)
- Plusieurs prix (ex. TTC, carton, négoce, e-commerce)
- Cases “Magasins” (YOP, Square, Bassam, Koumassi, etc.)

---

## 5) Équipe Inventaire Journalier

Chemin : **Inventaire → Configuration → Equipe Inventaire Journalier**

1. Créer une équipe
2. Renseigner :
   - **Chef d’équipe**
   - **Société**
   - **Membres**

Cette équipe est ensuite sélectionnable dans l’Inventaire Physique Journalier.

---

## 6) Inventaire Physique Journalier (process complet)

Chemin : **Inventaire → Opérations → Ajustements d’inventaire → Inventaire Physique Journalier**

### 6.1 Préparer l’inventaire

1. Créer un nouvel inventaire (depuis la liste)
2. Remplir :
   - **Catégorie Code Inventaire**
   - **Code Inventaire** (filtré par la catégorie)
   - **Équipe**
   - **Date**
   - (Société : souvent automatiquement)

### 6.2 Générer la liste d’articles à compter

- Cliquer **“Generer les articles”**

Résultat attendu : l’onglet **“Ligne Inventaire Physique”** se remplit.

### 6.3 Imprimer la fiche de comptage (optionnel, recommandé)

- Tant que l’inventaire est en comptage/brouillon, vous pouvez imprimer :
  - **“Imprimer fiche de comptage”**

C’est une liste avec des lignes à remplir au stylo (Qté Totale).

### 6.4 Soumettre pour vérification

- Cliquer **“Soumettre pour validation”**

Résultat attendu : l’état passe en **Vérification**.

### 6.5 Saisir les quantités comptées

Dans **Ligne Inventaire Physique** :

- Saisir **Qté comptée**
- Le système calcule :
  - **Différence** (écart)
  - **Valorisation** (impact estimé)

### 6.6 Retirer une ligne (si besoin)

- Sur une ligne : **“Retirer la ligne”**
- Elle passe dans l’onglet **“A vérifier”**
- Pour la remettre : **“Restaurer”**

### 6.7 Valider l’inventaire

- Cliquer **“Valider l’inventaire”** (selon vos droits)

Résultat attendu : l’état passe à **Terminé** et la **date de fin** est remplie.

### 6.8 Imprimer le rapport final

Quand l’inventaire est **Terminé** :

- **Imprimer Inventaire** : rapport complet (théorique, compté, écart, valorisation)

---

## 7) Transfert Inter Magasin (inter-entreprises)

Chemin : **Inventaire → Opérations → Transferts → Transfert Inter Magasin**

### 7.1 Créer un transfert

1. Créer un transfert
2. Dans la zone **Source** :
   - (si utilisé) Fournisseur/Partenaire
   - **Recevoir de** (société source)
   - Date planifiée / origine
3. Dans la zone **Destination** :
   - **Société qui reçoit**
   - Type d’opération / emplacements (souvent remplis automatiquement)

### 7.2 Ajouter plusieurs produits rapidement

- Cliquer **“Ajouter produits (multiple)”**
- Sélectionner les produits
- Valider

### 7.3 Confirmer

- Cliquer **“Confirmé”**

Important : un message rappelle de vérifier que les sociétés concernées sont bien cochées/renseignées.

Résultat attendu (simplifié) :

- Le système prépare les mouvements pour la société qui **reçoit** et la société qui **envoie**.

### 7.4 Annuler / retour brouillon

- **Annulé** : possible uniquement si les opérations liées ne sont pas terminées.
- **Mettre en brouillon** : supprime les transferts générés tant que ce n’est pas “fait”.

---

## 8) Règles de réapprovisionnement & fournisseur principal

### 8.1 Marquer un fournisseur principal

Dans la liste des fournisseurs d’un produit (prix fournisseur) :

- Cocher **Fournisseur principal** sur le bon fournisseur

Règle : un seul fournisseur principal par produit (si vous en cochez un autre, l’ancien sera décoché).

### 8.2 Mettre à jour les fournisseurs depuis les règles de réapprovisionnement

Chemin : **Inventaire → Configuration → Règles de réapprovisionnement**

- (Recommandé) Sélectionner d’abord les lignes concernées, puis utiliser le bouton **“Mettre à jour les fournisseurs”**.

Résultat attendu :

- si un fournisseur principal existe pour le produit → il est pris en priorité
- sinon → un fournisseur “par défaut” est sélectionné s’il existe

---

## 9) Ventes : saisie par Code Article

Dans un devis/commande :

- La colonne **Code Article** est disponible sur les lignes.

Usage :

- Saisir/Scanner un **Code Article** → le produit est automatiquement proposé/rempli.

---

## 10) Checklist de test (rapide)

### Paramétrage

- [ ] Je peux créer une **Catégorie code inventaire** et un **Code inventaire** lié.
- [ ] Je peux créer un **Rayon** + **Sous rayon**.
- [ ] Je peux créer une **Famille** + **Sous famille**.
- [ ] Je peux renseigner ces champs sur une **fiche produit**.

### Inventaire physique

- [ ] Je crée un **Inventaire Physique Journalier**.
- [ ] Je clique **Generer les articles** → les lignes apparaissent.
- [ ] J’imprime la **fiche de comptage**.
- [ ] Je clique **Soumettre pour validation**.
- [ ] Je saisis des Qté comptées et je vois les écarts.
- [ ] Je retire une ligne puis je la restaure depuis “A vérifier”.
- [ ] Je valide l’inventaire (si j’ai le droit) et j’imprime le **rapport final**.

### Transfert inter magasin

- [ ] Je crée un transfert, j’ajoute plusieurs produits via le bouton “multiple”.
- [ ] Je confirme le transfert.

### Réappro

- [ ] Je définis un **Fournisseur principal** sur un produit.
- [ ] Je clique **Mettre à jour les fournisseurs** sur les règles de réapprovisionnement.

---

## 11) Problèmes fréquents (et quoi faire)

- **“Vous devez d'abord créer les lignes…”** lors de la soumission :
  - Cliquez d’abord **Generer les articles**.
- **Impossible de supprimer un inventaire** :
  - Il doit être en état **Brouillon/Comptage**.
- **Bouton “Valider l’inventaire” absent** :
  - Vérifier vos droits/profil (demander au responsable).
- **Je ne peux pas créer un produit** :
  - Vous n’avez probablement pas le rôle **Administrateur Produits**.

---

### Emplacements “captures d’écran” (optionnel)

- [Capture] Inventaire Physique Journalier — écran principal
- [Capture] Bouton “Generer les articles”
- [Capture] Onglet “A vérifier” (archivage/restauration)
- [Capture] Transfert Inter Magasin — ajout produits multiple
- [Capture] Règles de réapprovisionnement — bouton mise à jour fournisseurs
