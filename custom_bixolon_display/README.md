# Module Afficheur Client Bixolon BCD-2000
## `custom_bixolon_display` — Odoo 19 / Point de Vente

---

## Table des matières

1. [Présentation](#1-présentation)
2. [Prérequis matériels et logiciels](#2-prérequis-matériels-et-logiciels)
3. [Installation du module](#3-installation-du-module)
4. [Configuration unique sur le PC caisse (Edge)](#4-configuration-unique-sur-le-pc-caisse-edge)
5. [Installation du driver Bixolon](#5-installation-du-driver-bixolon)
6. [Activation dans la config POS](#6-activation-dans-la-config-pos)
7. [Utilisation au quotidien](#7-utilisation-au-quotidien)
8. [Ce que voit le client sur l'afficheur](#8-ce-que-voit-le-client-sur-lafficheur)
9. [Dépannage](#9-dépannage)
10. [Notes techniques](#10-notes-techniques)

---

## 1. Présentation

Ce module intègre l'**afficheur client Bixolon BCD-2000** (afficheur VFD 2 lignes × 20 caractères) dans le Point de Vente Odoo 19, sans IoT Box et sans logiciel externe.

La communication passe par la **Web Serial API** du navigateur : le POS envoie directement les commandes au BCD-2000 via le câble USB, depuis Edge.

### Pourquoi pas le natif Odoo ?

Odoo "Customer Display" natif attend un **deuxième écran HDMI** ou un **IoT Box (Raspberry Pi)** avec un navigateur. Le BCD-2000 est un afficheur VFD série — incompatible avec ce système. Ce module comble ce manque.

---

## 2. Prérequis matériels et logiciels

| Élément | Requis |
|---|---|
| Afficheur | Bixolon BCD-2000 (modèle USB) |
| Connexion | Câble USB branché sur le PC caisse |
| Navigateur | **Microsoft Edge 89+** ou Google Chrome 89+ |
| OS caisse | Windows 10/11 |
| Odoo | Version 19, module `custom_pos` installé |
| Réseau | `http://172.16.8.178:8089` (préprod) |

---

## 3. Installation du module

### 3.1 Copier le module

Placer le dossier `custom_bixolon_display` dans :
```
/addons-sangel-19/custom_bixolon_display/
```

### 3.2 Installer via Odoo

```bash
# Méthode 1 — ligne de commande (recommandé)
python odoo-bin -u custom_bixolon_display -d NOM_BASE_DE_DONNEES

# Méthode 2 — interface Odoo
Paramètres → Modules → Rechercher "Bixolon" → Installer
```

### 3.3 Vérifier l'installation

Aller dans **POS → Configuration → Paramètres** : un onglet **"Afficheur Bixolon"** doit apparaître.

---

## 4. Configuration unique sur le PC caisse (Edge)

> Cette étape est nécessaire **une seule fois par PC caisse** car Odoo tourne en HTTP
> (`http://172.16.8.178:8089`). La Web Serial API requiert un contexte sécurisé.

### Étapes

1. Ouvrir un nouvel onglet Edge
2. Coller dans la barre d'adresse (ne pas chercher sur Google, taper directement) :
   ```
   edge://flags/#unsafely-treat-insecure-origin-as-secure
   ```
3. Dans le champ de texte qui apparaît sous **"Insecure origins treated as secure"**, entrer :
   ```
   http://172.16.8.178:8089
   ```
4. Dans le menu déroulant à droite, sélectionner **Enabled**
5. Cliquer le bouton **Relaunch** (Edge se redémarre)
6. Après redémarrage, l'URL Odoo est désormais traitée comme sécurisée

> Si vous changez d'URL Odoo (exemple : passage en production), répéter cette étape
> avec la nouvelle URL.

---

## 5. Installation du driver Bixolon

### 5.1 Vérifier si le driver est déjà installé

1. Brancher le BCD-2000 en USB sur le PC caisse
2. Ouvrir le **Gestionnaire de périphériques Windows** :
   - Touche Windows + R → taper `devmgmt.msc` → Entrée
3. Développer la section **Ports (COM & LPT)**

**Résultat attendu :**
```
Ports (COM & LPT)
  └─ Silicon Labs CP210x USB to UART Bridge (COM3)
     OU
  └─ Bixolon Customer Display (COM3)
```
Le numéro COM peut varier (COM3, COM4, etc.). **Notez ce numéro**, vous en aurez besoin.

### 5.2 Si le périphérique est inconnu (pas de driver)

Symptôme : Le Gestionnaire de périphériques affiche un point d'exclamation jaune sous **"Autres périphériques"** → **"Périphérique inconnu"**.

**Solution :**
1. Aller sur le site Bixolon : `https://www.bixolon.com`
2. Chercher "BCD-2000 driver" ou "CP210x driver"
3. Télécharger et installer le driver USB
4. Redémarrer le PC
5. Revérifier le Gestionnaire de périphériques

Alternativement, le driver CP210x (Silicon Labs) est disponible directement :
chercher "CP210x Windows Drivers" sur le site Silicon Labs.

---

## 6. Activation dans la config POS

1. Aller dans **POS → Configuration → Paramètres**
2. Ouvrir l'onglet **"Afficheur Bixolon"**
3. Cocher **"Activer l'afficheur Bixolon BCD-2000"**
4. Sauvegarder

Un guide de configuration s'affiche directement dans l'onglet pour rappeler les étapes.

---

## 7. Utilisation au quotidien

### 7.1 Premier démarrage après installation (connexion initiale)

1. Ouvrir le POS dans Edge
2. Un bouton **"Afficheur"** avec une icône télévision apparaît dans la barre du haut
3. Cliquer **"Afficheur"**
4. Edge affiche une fenêtre de sélection de port :

   ```
   ┌─────────────────────────────────────┐
   │  Sélectionner un port série         │
   │                                     │
   │  ○ Silicon Labs CP210x (COM3)       │
   │                                     │
   │              [Annuler] [Connecter]  │
   └─────────────────────────────────────┘
   ```

5. Sélectionner le port COM du BCD-2000 → cliquer **Connecter**
6. Le bouton passe en **vert** : `Afficheur ✓`
7. L'afficheur affiche le message de bienvenue :
   ```
   ┌────────────────────┐
   │   BIENVENUE !      │
   │   SANGEL YOP SARL  │
   └────────────────────┘
   ```

### 7.2 Démarrages suivants (reconnexion automatique)

La permission USB est mémorisée par Edge. Dès l'ouverture du POS, le module **reconnecte automatiquement** le BCD-2000 sans action de l'utilisateur.

Une notification verte confirme : *"Afficheur Bixolon BCD-2000 connecté."*

### 7.3 Déconnecter manuellement

Cliquer le bouton **"Afficheur ✓"** (vert) → le bouton redevient gris et l'afficheur est libéré.

---

## 8. Ce que voit le client sur l'afficheur

### Exemple de session complète

**Ouverture du POS**
```
┌────────────────────┐
│   BIENVENUE !      │
│   SANGEL YOP SARL  │
└────────────────────┘
```

**Caissier scanne : 2 kg de Poulet Fermier à 2 500 FCFA/kg**
```
┌────────────────────┐
│Poulet Fermier      │
│2x 2 500,00 FCFA    │
└────────────────────┘
```

**Caissier ajoute : 1 Coca Cola 500ml à 500 FCFA**
```
┌────────────────────┐
│Coca Cola 500ml     │
│1x 500,00 FCFA      │
└────────────────────┘
```

**Caissier clique "Paiement" (total = 5 500 FCFA)**
```
┌────────────────────┐
│TOTAL A PAYER :     │
│     5 500,00 FCFA  │
└────────────────────┘
```

**Client paie 6 000 FCFA (rendu = 500 FCFA)**
```
┌────────────────────┐
│  *** MERCI ! ***   │
│Rendu : 500,00 FCFA │
└────────────────────┘
```

**Nouvelle commande (commande vide)**
```
┌────────────────────┐
│   BIENVENUE !      │
│   SANGEL YOP SARL  │
└────────────────────┘
```

---

## 9. Dépannage

### Le bouton "Afficheur" n'apparaît pas dans le POS

- Vérifier que la case est cochée dans **POS → Configuration → Paramètres → Afficheur Bixolon**
- Rafraîchir le POS (F5)
- Si module installé récemment, mettre à jour le module : `-u custom_bixolon_display`

---

### Clic sur "Afficheur" → dialog "Configuration Edge requise"

**Cause :** L'étape 4 (flag Edge) n'a pas été faite ou la mauvaise URL a été saisie.

**Solution :**
1. Aller sur `edge://flags/#unsafely-treat-insecure-origin-as-secure`
2. Vérifier que `http://172.16.8.178:8089` est bien dans le champ (sans slash final)
3. Vérifier que le menu déroulant est sur **Enabled**
4. Cliquer **Relaunch**

---

### Clic sur "Afficheur" → aucun port ne s'affiche dans la fenêtre Edge

**Cause :** Driver Bixolon non installé ou câble USB non branché.

**Solution :**
1. Vérifier le câble USB (essayer un autre port USB)
2. Ouvrir le Gestionnaire de périphériques → vérifier Ports (COM & LPT)
3. Si périphérique inconnu → installer le driver (voir section 5.2)
4. Redémarrer le PC après installation du driver

---

### Le port apparaît dans Edge mais "Impossible d'ouvrir le port"

**Cause :** Un autre logiciel utilise déjà le port COM (ex: Bixolon SDK, terminal série, etc.).

**Solution :**
1. Fermer tout logiciel qui pourrait accéder au port COM
2. Si un onglet Edge du POS était déjà ouvert avec le port connecté, le fermer
3. Réessayer

---

### L'afficheur est connecté (bouton vert) mais ne s'actualise pas

**Cause possible :** Câble USB débranché puis rebranché sans déconnecter dans le POS.

**Solution :**
1. Cliquer le bouton **"Afficheur ✓"** pour déconnecter
2. Rebrancher le USB
3. Recliquer **"Afficheur"** pour reconnecter

---

### Les caractères accentués s'affichent mal (é → ?, à → ?)

**Cause :** Le BCD-2000 est un afficheur VFD avec encodage ASCII/CP437, pas UTF-8.

Le module remplace automatiquement les caractères accentués par leur équivalent ASCII (é→e, à→a, etc.) pour garantir un affichage propre. Si des `?` apparaissent, vérifier la configuration du display dans les paramètres internes du BCD-2000 (DIP switches, si applicable).

---

### Déconnexion automatique pendant une session

**Cause :** Coupure USB, mise en veille du PC, ou erreur de port série.

**Solution :** Cliquer le bouton **"Afficheur"** (gris) pour reconnecter. Si le port a changé de numéro COM, sélectionner le bon dans la fenêtre Edge.

---

## 10. Notes techniques

### Architecture du module

```
custom_bixolon_display/
├── models/pos_config.py          Champ has_bixolon_display sur pos.config
├── static/src/js/
│   ├── bixolon_service.js        BixolonDisplayManager (Web Serial, protocole VFD)
│   └── bixolon_pos_patch.js      Patches OWL : CustomerDisplayPosAdapter + Navbar
├── static/src/xml/bixolon.xml    Bouton dans la navbar POS
└── views/pos_config_views.xml    Onglet config POS
```

### Ce que le module ne touche pas

- Aucune modification de `custom_pos` ni des modules natifs
- Aucun `stock.move`, `account.move`, ni donnée financière
- Si `has_bixolon_display = False`, les patches ne s'exécutent pas

### Protocole BCD-2000

```
0x0C            = Effacer écran + curseur → ligne 1, col 1
[20 chars]      = Ligne 1 (ASCII, padding avec espaces)
\x1B[2;1H       = Séquence ANSI : curseur → ligne 2, col 1
[20 chars]      = Ligne 2 (ASCII, padding avec espaces)
Baud : 9600, 8N1
```

### Limitations connues

- Fonctionne uniquement sur Edge ou Chrome (pas Firefox, pas Safari)
- Requiert la configuration du flag Edge sur chaque PC caisse (une seule fois)
- Maximum 20 caractères par ligne (les noms trop longs sont tronqués)
- Les caractères non-ASCII (arabe, symboles spéciaux) apparaissent comme `?`

---

*Module développé pour SANGEL YOP — Odoo 19 — Partenaires Succès*
