# Cahier des charges — Plateforme de guilde WoW Forever

> Document vivant, construit étape par étape. Dernière mise à jour : 2026-10-27.

## Sommaire

1. [Cadrage](#1-cadrage) ✅
2. [Rôles et permissions](#2-rôles-et-permissions) ✅
3. [Comptes et personnages](#3-comptes-et-personnages) ✅
4. [Fiche de personnage](#4-fiche-de-personnage) ✅
5. [Base de données du jeu](#5-base-de-données-du-jeu) ✅
6. [Métiers](#6-métiers) ✅
7. [Agenda et événements](#7-agenda-et-événements) ✅
8. [Fonctionnalités annexes](#8-fonctionnalités-annexes) ✅
9. [Architecture technique](#9-architecture-technique) ✅
10. [MVP et feuille de route](#10-mvp-et-feuille-de-route) ✅

---

## 1. Cadrage

### Objectif

Petite plateforme web privée pour rassembler la guilde (entre potes) sur **World of Warcraft: Forever** :
chacun a son compte, on sait qui joue quoi, qui a quels métiers, et on organise les événements via un agenda.

### Contexte jeu

- **Version :** World of Warcraft: Forever (« Classic+ »), sortie le **4 novembre 2026**.
- Niveau max 60, Azeroth période 2004, classes « vanilla » + nouvelle race **Skyborn**.
- Le jeu est neuf et va évoluer (contenu ajouté sur la durée) → les listes de **classes, races, spécialisations,
  métiers** sont stockées en base comme **données de référence** (administrables), pas codées en dur.

### Décisions

| Sujet | Décision | Remarque |
|---|---|---|
| Stack | **Django** (backend/API) + **React** (frontend) | Détails à l'étape 9 |
| Authentification | **Discord OAuth2** + **sessions Django** | Pas de mot de passe à gérer côté site, pas de JWT (même origine) |
| Personnages | **Saisie manuelle** | Import auto via API Blizzard envisagé plus tard, si l'API couvre WoW Forever |
| Données du jeu | **Wowhead** pour les infobulles et fiches détaillées, **index local minimal** pour l'autocomplétion et les contrôles | Détails à l'étape 5 |
| Taille | **< 30 membres** | Pas d'enjeu de montée en charge |
| Hébergement | **Petit VPS** (Docker) | Détails à l'étape 9 |
| Langue | Français | |
| Support | **Mobile d'abord** | Un site de guilde se consulte surtout depuis le téléphone |
| Jalon | **Lots 0 et 1 en ligne le 4 novembre 2026** | Cf. étape 10 |

### Points ouverts

- Le modèle de données doit prévoir dès maintenant des champs « source » / identifiants externes sur les personnages,
  pour brancher l'import Blizzard plus tard sans migration douloureuse.

---

## 2. Rôles et permissions

### Accès au site

- Connexion **uniquement via Discord OAuth2** (avec paramètre `state` anti-CSRF).
- Seuls les membres du serveur Discord de la guilde **ayant le rôle Discord « Membre »** peuvent créer un compte
  et se connecter.

**Vérification à la connexion :**
1. Scope OAuth demandé : `identify` uniquement (écran de consentement minimal).
2. Le backend appelle, **avec le token du bot**, `GET /guilds/{ID_SERVEUR}/members/{ID_UTILISATEUR}`, qui renvoie
   le profil de membre sur **notre** serveur, dont la liste des **IDs de rôles**. L'application bot est donc créée
   dès le lot 0, mais seul son token est utilisé (pas de connexion à la gateway avant le lot 3).
3. Refus si : pas membre du serveur (réponse 404), ou aucun des rôles autorisés dans sa liste. Message explicite
   (« Tu dois avoir le rôle Membre sur le Discord de la guilde »).
4. Les rôles autorisés sont configurés par **ID de rôle** (pas par nom, qui peut être renommé), en variable
   d'environnement, sous forme de liste (ex. Membre, Officier, GM si ce sont des rôles Discord distincts).

**Révocation en continu (via le bot, lot 3) :**
- Le bot écoute les événements Discord « membre mis à jour » (perte du rôle) et « membre parti / banni » : le compte
  est **désactivé immédiatement** (pas supprimé : l'historique des événements reste cohérent).
- Django refuse un utilisateur inactif à chaque requête : l'accès est coupé **dès la requête suivante**, et ses
  sessions ouvertes sont supprimées.
- Si le rôle est rendu, le compte est réactivé à la prochaine connexion.
- Nécessite l'intent privilégié **Server Members** du bot (à activer dans le Discord Developer Portal).
- Avant la mise en service du bot, la révocation se fait uniquement à la connexion suivante ; un officier
  peut aussi désactiver un compte à la main.

> Le rôle Discord « Membre » sert **uniquement à l'accès**. Les rôles du site (GM / Officier / Membre) restent
> gérés sur le site.
- Le premier GM est désigné par configuration (ID Discord en variable d'environnement), les suivants via le site.

### Rôles

Rôles **gérés sur le site**, sans synchronisation avec les rôles Discord (le bot ne sert qu'à l'accès et aux
notifications).

| Rôle | Description |
|---|---|
| **GM** | Chef de guilde, tous les droits. Peut nommer/retirer des officiers. |
| **Officier** | Gère les membres et modère les événements. |
| **Membre** | Rôle par défaut à la première connexion. |

### Matrice des permissions

| Action | Membre | Officier | GM |
|---|:---:|:---:|:---:|
| Voir le roster, les personnages, les métiers, l'agenda | ✅ | ✅ | ✅ |
| Gérer **son** profil et **ses** personnages | ✅ | ✅ | ✅ |
| Créer un événement | ✅ | ✅ | ✅ |
| Modifier / annuler **son** événement | ✅ | ✅ | ✅ |
| Modifier / annuler **n'importe quel** événement | ❌ | ✅ | ✅ |
| S'inscrire / se désinscrire d'un événement | ✅ | ✅ | ✅ |
| Modifier les personnages d'un autre membre | ❌ | ✅ | ✅ |
| Désactiver / réactiver un membre | ❌ | ✅ | ✅ |
| Promouvoir / rétrograder un officier | ❌ | ❌ | ✅ |
| Gérer les données de référence (classes, métiers…) | ❌ | ❌ | ✅ |
| Proposer et voter dans un sondage, retirer **sa** proposition | ✅ | ✅ | ✅ |
| Créer / modifier un sondage, supprimer **n'importe quelle** proposition | ❌ | ✅ | ✅ |
| Valider le résultat d'un sondage | ❌ | ❌ | ✅ |

### Points ouverts

- Synchronisation des rôles avec Discord : écartée pour le MVP, réévaluable plus tard.

---

## 3. Comptes et personnages

### Paramètres de guilde

Guilde **mono-faction** : la faction et le royaume sont des **paramètres globaux** de la guilde (modifiables par le GM),
pas des champs par personnage. La liste des races proposées est filtrée selon la faction.

### Profil joueur

| Champ | Source | Remarque |
|---|---|---|
| Pseudo et avatar Discord | Discord (mis à jour à chaque connexion) | Lecture seule |
| Nom affiché | Joueur | Par défaut = pseudo Discord |
| Bio | Joueur | Texte libre, optionnel |
| Disponibilités | Joueur | Créneaux hebdomadaires récurrents (jour + heure début/fin, à l'heure pleine), fuseau Europe/Paris ; saisie par grille cliquable jour × heure |
| Rôle sur le site | GM/Officiers | GM / Officier / Membre (cf. étape 2) |

Une vue « disponibilités de la guilde » agrège les créneaux de tout le monde pour aider à choisir les horaires d'événements.

### Personnages

Un joueur peut avoir **plusieurs personnages**, dont **exactement un « main »** (s'il a au moins un perso).

| Champ | Obligatoire | Remarque |
|---|:---:|---|
| Nom | ✅ | Unique dans la guilde |
| Classe | ✅ | Donnée de référence |
| Race | ✅ | Donnée de référence, filtrée par faction et compatibilité race/classe |
| Niveau | ✅ | 1–60, mis à jour manuellement |
| Rôle principal | ✅ | Tank / Heal / DPS, filtré selon ce que la classe permet |
| Rôle secondaire | ❌ | Ex. druide Heal en principal, Tank en secondaire |
| Spécialisation | ❌ | **Saisie manuelle** (donnée de référence) ; **remplacée** par la déduction depuis le build de talents actif dès qu'il en existe un, cf. étape 4 |
| Métiers | ❌ | Métier × niveau de compétence, version légère dès le lot 1, cf. étape 6 |
| Main | ✅ | Booléen, un seul main par joueur |
| Note | ❌ | Texte libre |
| Source / ID externe | — | Technique : `manuel` pour l'instant, prépare l'import Blizzard |

### Données de référence

Stockées en base, administrables par le GM, pré-remplies au lancement :

- **Classes** (avec couleur officielle de classe pour l'affichage)
- **Races** (avec faction, ou « les deux » tant que celle de Skyborn n'est pas confirmée) — y compris **Skyborn**
- **Compatibilités race ↔ classe** (ex. Skyborn : guerrier, chasseur, voleur, druide, chaman, mage)
- **Spécialisations** par classe, avec les rôles possibles
- **Métiers** (cf. étape 6)

### Vues attendues

- **Roster** : tableau des mains (avec alts dépliables), filtrable/triable par classe, rôle, niveau.
- **Fiche joueur** : profil, disponibilités, liste de ses persos.
- **Fiche personnage** : infos du perso, équipement, talents, statistiques (cf. étape 4) et métiers.
- **Synthèse de composition** : nombre de Tanks / Heals / DPS et répartition par classe (mains, niveau 60 ou tous).

### Points ouverts

- Faction et royaume définitifs à renseigner dès que choisis.
- Compatibilités race/classe et restrictions de faction propres à WoW Forever à vérifier à la sortie du jeu.

---

## 4. Fiche de personnage

La fiche de personnage reproduit l'essentiel de la fenêtre personnage du jeu : **équipement**, **talents** et
**statistiques** (somme des stats brutes au MVP). Elle s'appuie sur l'index du jeu et les infobulles Wowhead (cf. étape 5).

### Principe de « projection »

Un joueur peut préparer son personnage **au-delà de son niveau actuel** (talents comme au niveau 60, équipement de
plus haut niveau). Tout ce qui n'est **pas encore accessible au niveau actuel** est :
- **affiché différemment** (ex. grisé / contour en pointillés, mention « projeté ») ;
- **exclu du calcul des statistiques**.

Quand le niveau du personnage est mis à jour, les éléments devenus accessibles basculent automatiquement en « acquis ».

### Équipement

- **Plusieurs sets nommés** par personnage (ex. « PvE », « PvP », « Résistance feu »), dont **un principal**.
  Possibilité de dupliquer un set.
- **Emplacements** (vanilla) : Tête, Cou, Épaules, Dos, Torse, Chemise, Tabard, Poignets, Mains, Taille, Jambes,
  Pieds, Doigt ×2, Bijou ×2, Main droite, Main gauche, À distance / Relique.
- Pour chaque emplacement : un **objet** de la base (recherche avec autocomplétion, filtrée par emplacement)
  + un **enchantement** optionnel (filtré par emplacement).
- **Contrôles** : type d'armure / d'arme utilisable par la classe, arme à deux mains ⇒ main gauche vide,
  objets uniques (ex. deux exemplaires d'un anneau unique), restriction de classe.
- Un objet dont le **niveau requis** dépasse le niveau du perso est accepté mais **projeté** (cf. ci-dessus).
- **Bonus de set** (ex. pièces de tier) détectés et affichés selon le nombre de pièces portées.
- **Affichage** façon fenêtre personnage : icônes, couleurs de qualité, infobulles au survol (cf. étape 5).

### Talents

- **Calculateur interactif** : 3 arbres par classe, règles vanilla (1 point par niveau à partir du niveau 10, soit
  **51 points au niveau 60**, paliers tous les 5 points investis dans l'arbre, prérequis entre talents).
- **On peut toujours remplir jusqu'à 51 points**, quel que soit le niveau du perso.
- **L'ordre d'attribution des points est enregistré** : les `niveau − 9` premiers points sont **acquis**,
  les suivants sont **projetés** (affichage distinct). Retirer un point n'est
  possible que si l'ordre reste valide (prérequis et paliers respectés à chaque étape).
- **Plusieurs builds nommés** par personnage (ex. « Raid », « PvP », « Leveling »), dont **un actif**.
- Dès qu'un build actif existe, la **spécialisation** affichée sur le roster est déduite de ce build (arbre avec le
  plus de points acquis) et remplace la saisie manuelle de l'étape 3.
- **Lien partageable** vers un build (lecture seule).

### Statistiques (MVP : somme des stats brutes)

Le MVP se limite à la **somme des statistiques brutes** de l'équipement acquis du set sélectionné, enchantements et
bonus de set compris : Force, Agilité, Endurance, Intelligence, Esprit, Armure, les cinq résistances, et les bonus
plats explicites portés par les objets (puissance d'attaque, puissance des sorts, soins, régénération de mana…).

- **Calcul côté backend** (source de vérité unique, testable, réutilisable par le bot), avec un endpoint de
  **prévisualisation** pour voir l'effet d'une modification avant de l'enregistrer.
- **Détail au survol** de chaque stat : part des objets, des enchantements, des bonus de set.
- La fiche permet de **choisir le set** dont on affiche les stats (ex. set de résistance feu).
- **Exclus** : éléments projetés, effets conditionnels ou aléatoires (procs), qui sont seulement décrits.

Ce périmètre couvre l'usage réel (comparer deux sets, vérifier un seuil de résistance) sans dépendre des formules
du jeu.

### Hors MVP

- **Stats dérivées** (points de vie, mana, % de critique, % de toucher, esquive, parade, compétence d'arme…) et
  **stats de base** par race, classe et niveau : nécessitent les formules et coefficients de WoW Forever, inconnus
  avant la sortie, et un gros travail de données. Le moteur est conçu en « sources » de stats additionnables pour
  les ajouter sans refonte.
- **Prise en compte des talents dans les stats** (+% de caractéristique, +crit, +toucher…) : partie la plus
  coûteuse (effets simples déductibles des données importées, les autres à coder au cas par cas).
- Buffs et consommables (interrupteurs de buffs).

### Points ouverts

- Effets d'objets non triviaux (« Équipé : … » hors bonus de stat simple) : seulement décrits, à modéliser au cas par
  cas si le besoin apparaît.

---

## 5. Base de données du jeu

### Principe : Wowhead fait le gros du travail

Le site **ne reconstruit pas une encyclopédie**. Wowhead couvre chaque version du jeu et couvrira WoW Forever
rapidement ; son **script d'infobulles** s'intègre sur n'importe quel site. Le site se contente donc de :

- stocker un **index local minimal** de ce dont il a besoin pour l'autocomplétion, les contrôles et la somme des
  stats, chaque entrée portant l'**ID Wowhead** ;
- afficher les **infobulles Wowhead** au survol de tout objet, sort ou talent, partout sur le site (équipement,
  recettes, demandes de craft…), et **lier** vers la fiche Wowhead pour le détail.

### Contenu de l'index local

| Données | Détails |
|---|---|
| **Objets** | ID Wowhead, nom FR / EN, icône, qualité, emplacement, type (armure/arme), niveau requis, restrictions de classe, stats brutes, unicité, set d'appartenance. Les effets « Équipé : … » sont seulement conservés en texte |
| **Sets d'objets** | Pièces, bonus par palier (texte + stats brutes si simples) |
| **Enchantements** | Effet (stats brutes), emplacement, source (métier, quête…) |
| **Talents** | Arbres par classe (nom, icône, fond), talents (position, rangs, prérequis, description par rang) |
| **Recettes** | cf. étape 6 |
| **Instances** | cf. étape 7, saisies à la main dès le lot 2 |

Hors index : sorts et techniques, stats de base par race/classe/niveau (cf. étape 4, hors MVP).

### Alimentation

1. **Import depuis les données client** via la commande Django `import_gamedata`, **rejouable et idempotente**,
   qui télécharge les tables DB2 exportées par **wago.tools** (produit `wowf`, le client WoW Forever, disponible
   depuis le 27 octobre 2026 ; `wow_classic_era` en secours). Les stats des objets sont décodées depuis les
   « pourcentages de budget » du client et la table RandPropPoints. Les **icônes** sont servies par le CDN
   Wowhead à partir de leur nom (pas de stockage local pour l'instant).
2. **Couche de surcharge** : ajouts et corrections manuels (GM, via l'admin) pour ce que l'import ne couvre pas
   encore. Une ligne cochée « gérée à la main » **survit aux réimports**. Le niveau requis d'une recette est
   **estimé** depuis ses paliers jaune/gris (le client ne stocke pas l'orange) et se corrige de la même façon.
3. Plus tard : synchronisation via l'API Blizzard si elle couvre WoW Forever.

### Consultation

- **Calculateur de talents « vierge »** (sans personnage), avec lien partageable.
- **Recherche d'objets** limitée à l'autocomplétion (nom, filtre par emplacement). Pour le reste : Wowhead.

### Hors MVP

- Encyclopédie interne complète (recherche d'objets multi-critères, sorts par classe, fiches détaillées).
- Infobulles maison, si celles de Wowhead s'avèrent insuffisantes ou indisponibles pour Forever.

### Points ouverts

- **Disponibilité des exports du client WoW Forever** et délai de couverture par Wowhead après la sortie.
- Conditions d'utilisation des données et icônes Blizzard — acceptable pour un site **privé et non commercial**, à
  confirmer. Conditions d'utilisation du script d'infobulles Wowhead à relire.

---

## 6. Métiers

### Métiers suivis

- **Principaux** (2 max par personnage) : Alchimie, Forge, Enchantement, Ingénierie, Herboristerie, Travail du cuir,
  Minage, Dépeçage, Couture.
- **Secondaires** (sans limite) : Cuisine, Secourisme, Pêche.
- Liste stockée en données de référence (cf. étape 3), ajustable si WoW Forever ajoute/modifie des métiers.

Pour chaque personnage × métier : **niveau de compétence** (0–300, mis à jour manuellement) et éventuelle
**spécialisation** (ex. Ingénierie gnome/gobeline, Forge d'armes/d'armures, Travail du cuir élémentaire/tribal/dragon).

### Version légère (lot 1)

Livrée avec le roster, sans catalogue de recettes : métiers et niveaux par personnage, affichés sur la fiche
personnage, plus une vue **« Métiers de la guilde »** (qui a quel métier, à quel niveau, filtrable par métier). C'est la
question numéro un d'une guilde qui level ; le catalogue ci-dessous vient compléter plus tard.

### Catalogue de recettes (lot 6)

Catalogue **complet** pré-rempli ; chaque joueur **coche les recettes connues** par ses personnages.

| Champ recette | Remarque |
|---|---|
| Nom | |
| Métier | |
| Niveau de compétence requis | |
| Objet produit (+ quantité) | Avec qualité/rareté pour la couleur d'affichage |
| Composants | Liste objet × quantité |
| Source | Formateur, drop, quête, réputation, vendeur… |
| Lien externe | Optionnel (ex. fiche Wowhead) |
| Spécifique WoW Forever | Booléen, pour distinguer les ajouts de Forever |

**Alimentation du catalogue :**
1. Import initial depuis les données de **WoW Classic Era** (base vanilla) via un script d'import (commande Django).
2. Ajouts/corrections manuels par le GM (et officiers ?) pour les recettes propres à WoW Forever.
3. Plus tard : synchronisation via l'API Blizzard si elle couvre WoW Forever.

### Recherche « qui sait crafter ? »

- Recherche par nom de recette ou d'objet → liste des personnages qui la connaissent, avec leur joueur.
- Filtre par métier et par niveau de compétence.

### Demandes de craft (MVP)

**Cycle de vie :** `Ouverte` → `Prise en charge` → `Livrée` (ou `Annulée` à tout moment par le demandeur / un officier).

| Champ | Remarque |
|---|---|
| Demandeur | Joueur connecté |
| Recette | Choisie dans le catalogue |
| Quantité | |
| Crafteur ciblé | Optionnel : un perso précis, sinon ouvert à tous ceux qui connaissent la recette |
| Composants fournis | Aucun / partiels / tous, + note |
| Note | Texte libre (pourboire, urgence…) |
| Crafteur assigné | Renseigné à la prise en charge |

**Vues :**
- « Mes demandes » (en tant que demandeur).
- « Demandes que je peux réaliser » (recettes connues par mes persos).
- Liste globale des demandes ouvertes.

### Points ouverts

- **Source de données du catalogue** : même stratégie qu'à l'étape 5 (export du client Forever, Classic Era en
  attendant). Risque : les recettes WoW Forever ne seront connues qu'à la sortie et au fil des découvertes → saisie
  manuelle au début.
- Notifications des demandes de craft (Discord ?) : à traiter à l'étape 8.

---

## 7. Agenda et événements

### Types d'événements

| Type | Instance | Composition |
|---|---|---|
| **Raid** | Raid ciblé (donnée de référence) | Taille max + besoins par rôle |
| **Donjon** | Donjon ciblé (donnée de référence) | 5 joueurs, ex. 1 Tank / 1 Heal / 3 DPS |
| **PvP** | Optionnel (champ de bataille) | Optionnelle |
| **Social / autre** | — | Optionnelle (souvent sans limite) |

Les **instances** (raids, donjons, champs de bataille) sont des données de référence : nom, type, taille, niveau
recommandé, spécifique WoW Forever ou non (Forever ajoute 9 donjons et 2 raids).

### Événement

| Champ | Obligatoire | Remarque |
|---|:---:|---|
| Titre | ✅ | Pré-rempli d'après l'instance |
| Type | ✅ | |
| Instance | ❌ | Filtrée selon le type |
| Date et heure de début | ✅ | Fuseau Europe/Paris |
| Durée / heure de fin | ❌ | |
| Description | ❌ | Markdown simple (consignes, prérequis, consommables…) |
| Organisateur | ✅ | Créateur par défaut |
| Taille max | ❌ | Pré-remplie d'après l'instance |
| Besoins par rôle | ❌ | Nb de Tanks / Heals / DPS souhaités |
| Niveau minimum | ❌ | Les persos sous ce niveau ne peuvent pas s'inscrire |
| Clôture des inscriptions | ❌ | Date/heure après laquelle on ne peut plus s'inscrire |
| Statut | ✅ | `Planifié` / `Annulé` / `Terminé` |

### Inscription

- Un joueur s'inscrit avec **un de ses personnages** et **un rôle** (parmi ceux possibles pour ce perso).
- **Statut** : `Présent` / `Peut-être` / `En retard` / `Absent`, + **commentaire** optionnel.
- Une seule inscription par joueur et par événement (changer de perso/rôle/statut = modifier son inscription).
- Possible jusqu'à la clôture ; ensuite seul l'organisateur ou un officier peut modifier.

### Composition (validée par l'organisateur)

- Les inscrits sont des **candidats**. L'organisateur (ou un officier/GM) place chacun en
  **Confirmé** ou **Banc** ; par défaut : **Non placé**.
- Vue composition : colonnes Tank / Heal / DPS, persos colorés par classe, compteurs « confirmés / besoin » par rôle.
- Les joueurs voient leur placement sur l'événement.

### Vues

- **Calendrier** mois / semaine, événements colorés par type.
- **Liste « À venir »** (et « Mes événements » : ceux où je suis inscrit ou organisateur).
- **Fiche événement** : infos, inscrits par statut, composition, bouton d'inscription rapide.
- Accueil : prochains événements + mes inscriptions en attente.

### Hors MVP

- **Événements récurrents** (ex. raid hebdomadaire) — en attendant, bouton **« Dupliquer »** pour recréer vite un événement.
- Rappels / notifications : à traiter à l'étape 8.

---

## 8. Fonctionnalités annexes

### Bot Discord (MVP)

Un **bot Discord** dédié à la guilde.

**Messages dans un salon de la guilde** (salon configurable) :
- Nouvel événement créé (titre, date, lien vers la fiche).
- Composition publiée par l'organisateur (bouton « Publier sur Discord » sur la fiche, pour éviter un message à
  chaque placement).
- Rappel avant un événement (délai configurable, ex. 1 h avant).
- Événement annulé ou modifié (date/heure).
- Nouvelle demande de craft.
- Sondage ouvert, rappel 24 h avant la fin des propositions et avant la fin des votes, résultat validé.

**Messages privés (MP)** au joueur concerné :
- Placement dans un événement : confirmé / banc.
- Demande de craft prise en charge / livrée (pour le demandeur).
- Nouvelle demande de craft le ciblant (pour le crafteur).
- Rappel personnel avant un événement où il est confirmé.

**Commandes slash** :
- `/events` — prochains événements.
- `/inscription <événement>` — s'inscrire (perso, rôle, statut).
- `/craft <recette ou objet>` — qui sait crafter quoi (livrée avec le lot 6).

**Préférences** : chaque joueur peut désactiver les MP (globalement ou par type : placement, rappels, crafts)
depuis son profil.

**Réglages** (GM, page Paramètres) : ID du salon des annonces, délai de rappel avant un événement (défaut 60 min).
Les rappels de sondage partent 24 h avant chaque échéance. Une notification en échec est retentée trois fois puis
marquée en erreur, visible dans l'admin.

### Sondages à propositions (MVP, lot 1)

Mécanisme **générique** : les membres proposent des réponses, puis votent. Premier usage : **choisir le nom de la
guilde** avant la sortie du jeu. Réutilisable ensuite (jour de raid, logo, nom du bot…).

**Sondage** (créé par un officier ou le GM) :

| Champ | Obligatoire | Remarque |
|---|:---:|---|
| Titre | ✅ | Ex. « Nom de la guilde » |
| Description | ❌ | Markdown simple (consignes, contexte) |
| Fin des propositions | ✅ | Date/heure, fuseau Europe/Paris |
| Fin des votes | ✅ | Strictement après la fin des propositions |
| Propositions max par personne | ✅ | Défaut **3** |
| Votes max par personne | ❌ | Vide = **illimité** (défaut) |
| Règle de format | ❌ | `libre` (défaut) ou `nom de guilde WoW` : 2–24 caractères, lettres (accents acceptés) et espaces simples, ni chiffres ni caractères spéciaux |
| Définit le nom de guilde | ❌ | Booléen : à la validation, la proposition gagnante devient le **nom de guilde** (paramètre de guilde, cf. étape 3) |
| Statut | ✅ | `Propositions` → `Votes` → `Clos` → `Validé` (transitions automatiques aux dates, sauf la validation) |

**Déroulement :**

1. **Phase propositions** (jusqu'à la fin des propositions) : chaque membre soumet jusqu'au maximum autorisé
   (texte + note optionnelle, ex. le sens ou la blague derrière le nom). Unicité **insensible à la casse** et aux
   espaces superflus. Un membre peut **retirer** sa proposition tant que la phase est ouverte, ce qui libère un
   emplacement et supprime les votes reçus ; pas de modification, on retire et on repropose. **Le vote est ouvert
   dès la première proposition.**
2. **Phase votes** (jusqu'à la fin des votes) : **un vote par membre et par proposition**, retirable à tout moment,
   sans limite de nombre sauf si le sondage en fixe une. Voter pour sa propre proposition est autorisé. Plus aucune
   proposition ne peut être ajoutée.
3. **Clôture** automatique à la fin des votes : classement par nombre de votes, puis par ancienneté de la proposition
   en cas d'égalité. Plus aucun vote possible.
4. **Validation par le GM** : le GM confirme la proposition gagnante (par défaut la première du classement) ou en
   choisit une autre du classement avec une **justification** affichée (ex. nom déjà pris sur le royaume). Si le
   sondage « définit le nom de guilde », le nom de guilde est mis à jour. Le sondage passe en `Validé`.

**Visibilité : tout est public.** Chaque proposition affiche son auteur, son nombre de votes et la liste des
votants, en temps réel pendant toute la durée du sondage.

**Modération :** les officiers et le GM peuvent supprimer n'importe quelle proposition et modifier les dates d'un
sondage en cours (prolongation). Un sondage ne peut être supprimé qu'avant sa première proposition.

**Vues :**
- Liste des sondages (en cours, puis clos / validés).
- **Fiche sondage** : compte à rebours de la phase en cours, formulaire de proposition avec compteur (ex. « 2/3 »),
  propositions triées par votes avec bouton voter / retirer mon vote, résultat validé mis en avant une fois le
  sondage terminé.
- Accueil : bannière pour chaque sondage en cours où je n'ai pas encore voté.

### Autres fonctionnalités

Aucune autre fonctionnalité annexe retenue pour le MVP. Idées écartées pour l'instant, à réévaluer :
annonces/news, export iCal, banque de guilde, suivi du loot / DKP.

### Visibilité

**Tout est privé** : aucune page accessible sans connexion (hormis la page de connexion).

### Points ouverts

- Le bot rend possible plus tard la **synchronisation des rôles Discord** (écartée à l'étape 2).

---

## 9. Architecture technique

### Vue d'ensemble

```
                 ┌──────────────────────── VPS (Docker Compose) ────────────────────────┐
 Navigateur ───► │ Caddy (HTTPS auto)                                                    │
                 │   ├── /        → build statique React                                 │
                 │   └── /api/*   → Django + DRF (gunicorn) ──┐                          │
                 │                                            ├──► PostgreSQL            │
                 │ Bot Discord (manage.py runbot) ────────────┘                          │
                 └───────────────────────────────────────────────────────────────────────┘
                        ▲                                    ▲
                 Discord OAuth2                     Discord Gateway / API
```

### Backend

| Élément | Choix |
|---|---|
| Langage / framework | Python 3.13, **Django 5.2 LTS** |
| API | **Django REST Framework**, schéma OpenAPI via **drf-spectacular** |
| Base de données | **PostgreSQL** |
| Authentification | **Discord OAuth2** (flux maison : échange du code, lecture de `/users/@me`, puis vérification du rôle via `GET /guilds/{id}/members/{user_id}` avec le token du bot) puis **session Django** classique |
| Bot | **discord.py**, lancé par `manage.py runbot`, accès direct à l'ORM. Le bot est asynchrone et l'ORM synchrone : **tout accès base passe par `sync_to_async`** (ou des helpers dédiés) |
| Tâches de fond | Pas de Celery/Redis : boucles `discord.ext.tasks` dans le bot |
| Admin | Django admin pour les données de référence et le dépannage |

**Stratégie de session :**
- Front et API sont servis par Caddy sur la **même origine** : pas besoin de JWT. On utilise les **sessions Django**
  (cookie `httpOnly`, `Secure`, `SameSite=Lax`) avec `SessionAuthentication` côté DRF et la protection CSRF de Django
  (le front lit le cookie `csrftoken` et renvoie l'en-tête `X-CSRFToken`).
- Après le callback Discord, le backend ouvre la session et redirige vers le front. Déconnexion = `logout()`.
- Un utilisateur **désactivé est refusé à la requête suivante** (comportement standard de Django) ; à la désactivation,
  ses sessions sont supprimées. Aucune fenêtre de 15 minutes, aucune rotation ni blacklist à gérer.

**Notifications (outbox) :** le site écrit des lignes dans une table `Notification` (type, destinataire ou salon,
payload, statut) ; le bot les dépile et les envoie. Les rappels d'événements sont générés par une boucle du bot qui
scrute les événements à venir. Découplage simple : si le bot est arrêté, rien n'est perdu.

**Découpage en apps Django :**

| App | Contenu |
|---|---|
| `accounts` | Utilisateur (ID Discord, rôle site, bio, préférences de notification), disponibilités, auth Discord/session |
| `guild` | Paramètres de guilde (nom, faction, royaume, ID serveur et salon Discord) |
| `gamedata` | Données de référence et index du jeu : classes, races, spécialisations, métiers, instances, objets, sets, enchantements, talents, recettes ; commandes d'import et surcharges |
| `characters` | Personnages, métiers des personnages, sets d'équipement, builds de talents, recettes connues |
| `stats` | Somme des statistiques brutes par set (sans modèle, logique pure et testée, conçue en « sources » additionnables) |
| `crafting` | Demandes de craft |
| `events` | Événements, inscriptions, placements |
| `polls` | Sondages à propositions, propositions, votes, validation du résultat |
| `notifications` | Outbox de notifications |
| `discordbot` | Bot, commandes slash, boucles de tâches, commande `runbot` |

### Frontend

| Élément | Choix |
|---|---|
| Build | **Vite** + **React** + **TypeScript** |
| Routage | **React Router** |
| Données serveur | **TanStack Query** ; client et types **générés depuis le schéma OpenAPI** (openapi-typescript) |
| UI | **Tailwind CSS** v4, thème sombre aux couleurs WoW, couleurs de classe officielles ; composants maison légers au lot 0, **shadcn/ui** ajouté à la demande quand les besoins grossissent (formulaires, dialogues, calendrier) |
| Responsive | **Mobile d'abord** : roster, agenda, inscription et métiers doivent être confortables sur téléphone ; la fenêtre d'équipement et le calculateur de talents peuvent être pensés pour l'écran large |
| Formulaires | react-hook-form + zod |
| Calendrier | Composant calendrier à choisir à l'implémentation (ex. FullCalendar ou vue maison) ; vue liste privilégiée sur mobile |
| Spécifique WoW | Script d'**infobulles Wowhead** ; composants maison : fenêtre d'équipement, calculateur de talents |

### Organisation du dépôt

```
wow-forever/
├── backend/          # projet Django (apps ci-dessus, bot inclus)
├── frontend/         # app Vite/React
├── deploy/           # docker-compose.yml, Caddyfile, scripts de sauvegarde
├── docs/             # ce cahier des charges, notes techniques
└── .github/workflows # CI
```

### Déploiement et exploitation

- **Docker Compose** sur le VPS : `caddy`, `web` (gunicorn), `bot`, `db` (PostgreSQL). Le front est buildé et servi
  en statique par Caddy.
- **HTTPS** automatique via Caddy (Let's Encrypt) → nécessite un **nom de domaine**.
- **Sauvegardes** : `pg_dump` quotidien, rétention ~14 jours, copie hors du VPS.
- **Secrets** en variables d'environnement (`.env` non versionné) : clé secrète Django, client ID/secret OAuth Discord,
  token du bot (nécessaire dès le lot 0 pour la vérification du rôle), ID du serveur Discord, IDs des rôles Discord
  autorisés, ID Discord du premier GM.
- **Dev local** : `docker compose` pour PostgreSQL, Django en `runserver`, Vite en dev avec proxy `/api`.
- **Icônes** du jeu stockées sur un volume et servies en statique par Caddy (cache long).

### Qualité

- Backend : **pytest-django**, **ruff** (lint + format).
- Frontend : **Vitest**, **oxlint** (linter livré avec le gabarit Vite, remplace ESLint), **Prettier**, `tsc -b`.
- **CI GitHub Actions** : lint, vérification des migrations, tests back et front, build du front sur chaque push / PR.

### Points ouverts

- Nom de domaine et fournisseur du VPS.
- Création de l'application Discord (OAuth + bot) dans le Discord Developer Portal.

---

## 10. MVP et feuille de route

Principe : mettre en ligne au plus vite ce qui sert dès la sortie du jeu (qui joue quoi, qui a quel métier, sorties
de groupe), puis le bot, et seulement ensuite les grosses briques (données du jeu, fiche de personnage), dont le
périmètre a été réduit pour s'appuyer sur Wowhead.

| Lot | Cible | Contenu | Sections |
|---|---|---|---|
| **0 — Socle** | **4 nov. 2026** | Dépôt (backend/frontend/deploy), Docker, CI, connexion Discord + session avec contrôle du rôle Discord « Membre » via le token du bot, rôles du site, paramètres de guilde, déploiement sur le VPS | 1, 2, 9 |
| **1 — Roster, métiers légers, sondages** | **4 nov. 2026** | Profils, disponibilités, personnages (classe, race, niveau, rôles, spé manuelle, main/alts), métiers × niveau par personnage, roster, « Métiers de la guilde », synthèse de composition, **sondages à propositions** (premier usage : nom de la guilde). Classes, races et métiers saisis à la main | 3, 6, 8 |
| **2 — Agenda** | mi-nov. 2026 | Événements, inscriptions, composition validée, calendrier, bouton « Dupliquer ». Instances saisies à la main | 7 |
| **3 — Bot Discord** | fin nov. 2026 | Notifications en salon et en MP, rappels, commandes slash, révocation d'accès en temps réel | 8, 2 |
| **4 — Données du jeu** | déc. 2026 | Import de l'index (objets, sets, enchantements, talents, recettes, icônes) depuis le client Forever ou Classic Era en attendant, surcharges, infobulles Wowhead, calculateur de talents vierge | 5 |
| **5 — Fiche de personnage** | — | Sets d'équipement, calculateur de talents et builds, projection, somme des stats brutes | 4 |
| **6 — Catalogue et crafts** | — | Catalogue de recettes, recettes connues, « qui sait crafter ? », demandes de craft | 6 |

Les cibles des lots 0 à 4 sont indicatives ; les lots 5 et 6 seront datés une fois le lot 3 livré, et leur périmètre
réévalué à la lumière de la couverture de WoW Forever par Wowhead.

### Après le MVP (backlog)

- Stats dérivées et stats de base dans le moteur (points de vie, crit, toucher, esquive…), puis talents, puis
  buffs / consommables.
- Encyclopédie interne complète et infobulles maison.
- Événements récurrents.
- Synchronisation des rôles du site avec les rôles Discord.
- Import automatique des personnages via l'API Blizzard (si elle couvre WoW Forever).
- Annonces, export iCal, banque de guilde, suivi du loot / DKP.
