# Guide utilisateur — Surveillance des prix & étiquettes (module `custom_price_change_tracker`)

Ce guide décrit **ce que voit et fait l’utilisateur** dans Odoo après installation du module **Suivi des modifications de prix**.

> Objectif :
>
> - enregistrer automatiquement un **historique** à chaque changement de prix,
> - recevoir une **notification quotidienne** des changements,
> - **imprimer des étiquettes** (avec date d’impression),
> - générer des **rapports PDF** (historique et analyse).

---

## 1) Pour qui ?

- **Magasin / Stock** : contrôle et suivi des prix, impression d’étiquettes.
- **Administration / Direction** : validation, suivi des variations.
- **Back-office** : paramétrage des notifications.

---

## 2) Où trouver les menus ?

Dans l’application **Inventaire / Stock** (selon votre base), vous verrez un nouveau bloc :

- **Surveillance Prix**
  - **Historique des prix**
  - **Créer un Rapport**
  - **Analyse des Prix**

> Astuce : si vous ne voyez pas “Surveillance Prix”, vérifiez vos droits (voir section “Problèmes fréquents”).

---

## 3) Ce qui se passe automatiquement (important)

### A. L’historique se crée tout seul

Dès qu’un utilisateur modifie le **prix de vente** d’un produit, Odoo enregistre automatiquement une ligne dans **Historique des prix** avec :

- le produit,
- l’ancien prix et le nouveau prix,
- la date/heure,
- “Modifié par”.

✅ Vous n’avez **rien** à créer manuellement pour l’historique.

### B. Notifications quotidiennes (si activées)

Si l’option est activée, Odoo envoie chaque jour une notification dans un canal **Discussion** (chat), avec la liste des changements de prix détectés.

---

## 4) Paramétrage — Activer les notifications et choisir qui reçoit

1) Aller dans **Inventaire / Stock → Configuration → Paramètres**
2) Descendre jusqu’au bloc **Surveillance des Prix**
3) Cocher **Notifications de prix**
4) Dans **Utilisateur à notifier**, sélectionner un ou plusieurs utilisateurs
5) **Enregistrer**

✅ Résultat attendu :

- chaque jour (horaire système), les utilisateurs choisis reçoivent un message dans Discussion.

Bonnes pratiques :

- sélectionner au moins **1 responsable** (ex: Chef magasin)
- éviter de notifier trop de monde (sinon “bruit”)

---

## 5) Workflow 1 — Voir l’historique des changements de prix

1) Aller dans **Surveillance Prix → Historique des prix**
2) Utiliser la barre de recherche et les filtres (exemples) :
   - **Non notifiés** / **Notifiés**
   - **Hausses de prix** / **Baisses de prix**
   - **Variations importantes (>10%)**
   - **Aujourd’hui / Hier / Semaine passée / Mois passé**

✅ Résultat attendu :

- chaque ligne affiche l’ancien prix, le nouveau prix, la différence, le % de variation et l’utilisateur.

Astuce lecture rapide :

- les hausses peuvent apparaître en style “positif”, les baisses en “négatif” (selon affichage).

---

## 6) Workflow 2 — Marquer une ligne “Notifié” / “En attente”

Dans **Historique des prix**, ouvrir une ligne.

- Bouton **Marquer comme notifié** : met la ligne au statut “Notifié”.
- Bouton **Mettre en attente** : remet la ligne au statut “En attente”.

✅ Résultat attendu :

- le statut permet de distinguer ce qui a été traité / communiqué.

---

## 7) Workflow 3 — Notification quotidienne (où la voir ?)

Quand il y a eu des changements de prix, un message est posté dans **Discussion** dans un canal nommé :

- **Notifications sur le changement de prix**

Le message contient :

- les produits concernés,
- ancien prix → nouveau prix,
- différence et %,
- un lien “**Voir la liste des produits pour impression d’étiquettes**”.

✅ Résultat attendu :

- en cliquant le lien, vous ouvrez directement la liste filtrée des changements concernés.

---

## 8) Workflow 4 — Imprimer des étiquettes depuis l’historique

### A. Imprimer depuis une ligne (fiche)

1) Ouvrir une ligne dans **Historique des prix**
2) Si la ligne est au statut **Notifié**, cliquer **Imprimer étiquette**

✅ Résultat attendu :

- Odoo génère un PDF d’étiquettes pour le(s) produit(s).
- La ligne passe au statut **Imprimé** (statut impression).

### B. Imprimer en masse depuis la liste

1) Aller dans **Historique des prix**
2) Sélectionner plusieurs lignes
3) Lancer l’action **Imprimer Étiquettes** (menu Actions)

✅ Résultat attendu :

- impression en lot des étiquettes.

Note : les étiquettes peuvent afficher “**imprimé le …**” (date/heure) sur l’étiquette.

---

## 9) Workflow 5 — Générer un PDF “Historique des changements de prix”

1) Aller dans **Surveillance Prix → Créer un Rapport**
2) Choisir un **Type de période** (quotidien, hebdo, mensuel, personnalisé, …)
3) Vérifier/ajuster les dates **Date de début** et **Date de fin**
4) Onglet **Aperçu des données** : contrôler la liste
5) Cliquer **Imprimer**

✅ Résultat attendu :

- un PDF est généré avec la liste des changements sur la période.

---

## 10) Workflow 6 — Générer un PDF “Analyse des Prix” (Top produits les plus modifiés)

1) Aller dans **Surveillance Prix → Analyse des Prix**
2) Choisir la période
3) (Optionnel) Filtrer par :
   - **Produits** (laisser vide = tous)
   - **Catégories**
4) Vérifier l’aperçu
5) Cliquer **Imprimer le rapport**

✅ Résultat attendu :

- un PDF “Analyse des Prix Produits” avec :
  - la liste des produits et le **nombre de changements**,
  - un **TOP 5** des produits les plus fréquents.

---

## 11) Problèmes fréquents (et solutions simples)

### A. Je ne vois pas le menu “Surveillance Prix”

- Vérifier que vous avez un profil **Stock / Inventaire** (ex: Utilisateur Stock).
- Vérifier que le module est bien installé.

### B. Les notifications ne partent pas

À vérifier :

- l’option **Notifications de prix** est cochée
- au moins 1 utilisateur est sélectionné dans **Utilisateur à notifier**
- il y a eu des changements de prix sur la période (sinon pas de message)

### C. Le bouton “Imprimer étiquette” n’apparaît pas

- Sur une ligne d’historique, l’impression peut être liée au statut **Notifié**.
- Solution : cliquer **Marquer comme notifié**, puis réessayer.

### D. Je veux imprimer des étiquettes “propres”

- Filtrer d’abord l’historique (ex: “Aujourd’hui” + “Non notifiés”),
- puis imprimer en masse.

---

## 12) Check-list de test rapide (10–15 minutes)

1) **Activer la notification**

- activer “Notifications de prix”
- choisir 1 utilisateur

2) **Provoquer un changement**

- ouvrir un produit
- modifier le **prix de vente**
- enregistrer

3) **Vérifier l’historique**

- Surveillance Prix → Historique des prix
- vérifier la nouvelle ligne (ancien/nouveau + utilisateur)

4) **Tester le statut**

- ouvrir la ligne
- “Marquer comme notifié”, puis “Mettre en attente”

5) **Imprimer une étiquette**

- mettre la ligne “Notifié”
- cliquer “Imprimer étiquette”

6) **Rapports PDF**

- Créer un Rapport → Imprimer
- Analyse des Prix → Imprimer le rapport

---

## 13) Emplacements pour captures d’écran

- [CAPTURE] Menu : Inventaire/Stock → Surveillance Prix
- [CAPTURE] Liste : Historique des prix (colonnes ancien/nouveau/diff/%/statut)
- [CAPTURE] Paramètres : bloc “Surveillance des Prix” + utilisateurs à notifier
- [CAPTURE] Discussion : canal “Notifications sur le changement de prix”
- [CAPTURE] Fiche historique : boutons “Marquer comme notifié” + “Imprimer étiquette”
- [CAPTURE] PDF : Rapport Historique des Prix
- [CAPTURE] PDF : Analyse des Prix (Top 5)
