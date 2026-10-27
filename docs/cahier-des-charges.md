# Cahier des charges — Plateforme de guilde WoW Forever

> Document vivant, construit étape par étape. Dernière mise à jour : 2026-10-27.

## Sommaire

1. [Cadrage](#1-cadrage) ✅
2. [Rôles et permissions](#2-rôles-et-permissions) ✅
3. [Comptes et personnages](#3-comptes-et-personnages) ✅
4. [Fiche de personnage](#4-fiche-de-personnage) ✅
5. [Base de données du jeu et encyclopédie](#5-base-de-données-du-jeu-et-encyclopédie) ✅
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
| Authentification | **Discord OAuth2** | Pas de mot de passe à gérer côté site |
| Personnages | **Saisie manuelle** | Import auto via API Blizzard envisagé plus tard, si l'API couvre WoW Forever |
| Taille | **< 30 membres** | Pas d'enjeu de montée en charge |
| Hébergement | **Petit VPS** (Docker) | Détails à l'étape 9 |
| Langue | Français | |

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
1. Scopes OAuth demandés : `identify` + `guilds.members.read`.
2. Avec le token de l'utilisateur, le backend appelle `GET /users/@me/guilds/{ID_SERVEUR}/member`, qui renvoie
   le profil de membre sur **notre** serveur, dont la liste des **IDs de rôles**.
3. Refus si : pas membre du serveur (réponse 404), ou aucun des rôles autorisés dans sa liste. Message explicite
   (« Tu dois avoir le rôle Membre sur le Discord de la guilde »).
4. Les rôles autorisés sont configurés par **ID de rôle** (pas par nom, qui peut être renommé), en variable
   d'environnement, sous forme de liste (ex. Membre, Officier, GM si ce sont des rôles Discord distincts).

**Révocation en continu (via le bot) :**
- Le bot écoute les événements Discord « membre mis à jour » (perte du rôle) et « membre parti / banni » : le compte
  est **désactivé immédiatement** (pas supprimé : l'historique des événements reste cohérent).
- Comme chaque refresh de JWT vérifie que le compte est actif, l'accès est coupé au plus tard à l'expiration de
  l'access token (~15 min).
- Si le rôle est rendu, le compte est réactivé à la prochaine connexion.
- Nécessite l'intent privilégié **Server Members** du bot (à activer dans le Discord Developer Portal).
- Avant la mise en service du bot (lot 5), la révocation se fait uniquement à la connexion suivante ; un officier
  peut aussi désactiver un compte à la main.

> Le rôle Discord « Membre » sert **uniquement à l'accès**. Les rôles du site (GM / Officier / Membre) restent
> gérés sur le site.
- Le premier GM est désigné par configuration (ID Discord en variable d'environnement), les suivants via le site.

### Rôles

Rôles **gérés sur le site** (pas de synchronisation avec les rôles Discord, pas de bot nécessaire).

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
| Disponibilités | Joueur | Créneaux hebdomadaires récurrents (jour + heure début/fin), fuseau Europe/Paris |
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
| Spécialisation | — | **Déduite** du build de talents actif (arbre le plus investi), cf. étape 4 |
| Main | ✅ | Booléen, un seul main par joueur |
| Note | ❌ | Texte libre |
| Source / ID externe | — | Technique : `manuel` pour l'instant, prépare l'import Blizzard |

### Données de référence

Stockées en base, administrables par le GM, pré-remplies au lancement :

- **Classes** (avec couleur officielle de classe pour l'affichage)
- **Races** (avec faction) — y compris **Skyborn**
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
**statistiques calculées**. Elle s'appuie sur la base de données du jeu (cf. étape 5).

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
- La **spécialisation** affichée sur le roster est déduite du build actif (arbre avec le plus de points acquis).
- **Lien partageable** vers un build (lecture seule).

### Statistiques (fiche complète)

**Calcul côté backend** (source de vérité unique, testable, réutilisable par le bot), avec un endpoint de
**prévisualisation** pour voir l'effet d'une modification avant de l'enregistrer.

**Entrées du calcul :**
- Stats de base selon **race, classe et niveau** ;
- **Équipement acquis** du set sélectionné + enchantements + bonus de set.

**Exclus :**
- **Talents** : aucun effet de talent n'est pris en compte dans les stats pour l'instant (cf. hors MVP) ;
- éléments projetés ;
- buffs et consommables (des interrupteurs de buffs pourront venir plus tard) ;
- effets conditionnels ou aléatoires (procs), qui sont seulement décrits.

**Statistiques affichées :**

| Catégorie | Statistiques |
|---|---|
| Générales | Force, Agilité, Endurance, Intelligence, Esprit, Points de vie, Mana / Rage / Énergie, Armure |
| Résistances | Arcane, Feu, Givre, Nature, Ombre |
| Mêlée | Puissance d'attaque, Dégâts et vitesse d'arme, Toucher, Critique, Compétence d'arme |
| Distance | Puissance d'attaque à distance, Dégâts et vitesse, Toucher, Critique |
| Sorts | Puissance des sorts (par école), Puissance de soins, Critique, Toucher, Régénération de mana (5 s) |
| Défense | Défense, Esquive, Parade, Blocage, Valeur de blocage |

- **Détail au survol** de chaque stat : part de base, des objets, des enchantements, des bonus de set.
- La fiche permet de **choisir le set** dont on affiche les stats (ex. set PvP).
- **Formules** : celles de **WoW Classic Era** comme base ; les coefficients (par classe, par niveau) sont stockés en
  données pour pouvoir être ajustés si WoW Forever les modifie.

### Hors MVP

- **Prise en compte des talents dans les stats** (+% de caractéristique, +crit, +toucher…) : c'est la partie la plus
  coûteuse du moteur (effets simples déductibles des données importées, les autres à coder au cas par cas), reportée.
  Le moteur est conçu pour pouvoir ajouter cette source plus tard sans refonte (une « source » de stats parmi d'autres).

### Points ouverts

- Effets d'objets non triviaux (« Équipé : … » hors bonus de stat simple) : à modéliser au cas par cas.
- Formules et stats de base de WoW Forever (et de la race Skyborn) inconnues avant la sortie.

---

## 5. Base de données du jeu et encyclopédie

### Contenu

| Données | Détails |
|---|---|
| **Objets** | Nom, icône, qualité, emplacement, type (armure/arme), niveau d'objet, niveau requis, restrictions de classe, stats, effets (« Équipé : … », « Utilisation : … »), unicité, set d'appartenance |
| **Sets d'objets** | Pièces, bonus par palier |
| **Enchantements** | Effet, emplacement, source (métier, quête…) |
| **Sorts et techniques** | Classe, rang, niveau d'apprentissage, coût, temps d'incantation, portée, temps de recharge, description, icône |
| **Talents** | Arbres par classe (nom, icône, fond), talents (position, rangs, prérequis, description par rang) |
| **Stats de base** | Par race, classe et niveau |
| **Recettes** | cf. étape 6 |
| **Instances** | cf. étape 7 |

Données en **français** (avec le nom anglais conservé pour la recherche et les liens externes).

### Alimentation

1. **Import initial depuis les données client de WoW Classic Era** (exports des tables du jeu) via des commandes
   Django **rejouables et idempotentes** ; **icônes** téléchargées et servies par notre propre serveur.
2. **Couche de surcharge « Forever »** : ajouts et corrections manuels (GM, via l'admin) pour le contenu propre à
   WoW Forever (nouveaux objets, sorts, talents, race Skyborn…). Ces surcharges **survivent aux réimports**.
3. Plus tard : synchronisation via l'API Blizzard si elle couvre WoW Forever.

### Encyclopédie (consultation)

- **Recherche d'objets** avec filtres (emplacement, type, qualité, niveau, classe, statistique) et fiche objet.
- **Sorts par classe**, classés par niveau d'apprentissage, avec leurs rangs.
- **Calculateur de talents « vierge »** (sans personnage), avec lien partageable.
- **Infobulles façon WoW** au survol de tout objet, sort ou talent, partout sur le site (équipement, recettes,
  demandes de craft…).

### Points ouverts

- **Source exacte des données** Classic Era (outil d'export des tables du jeu) et conditions d'utilisation des
  données et icônes Blizzard — acceptable pour un site **privé et non commercial**, à confirmer.
- Ampleur des différences entre Classic Era et WoW Forever, connue seulement après la sortie.

---

## 6. Métiers

### Métiers suivis

- **Principaux** (2 max par personnage) : Alchimie, Forge, Enchantement, Ingénierie, Herboristerie, Travail du cuir,
  Minage, Dépeçage, Couture.
- **Secondaires** (sans limite) : Cuisine, Secourisme, Pêche.
- Liste stockée en données de référence (cf. étape 3), ajustable si WoW Forever ajoute/modifie des métiers.

Pour chaque personnage × métier : **niveau de compétence** (0–300, mis à jour manuellement) et éventuelle
**spécialisation** (ex. Ingénierie gnome/gobeline, Forge d'armes/d'armures, Travail du cuir élémentaire/tribal/dragon).

### Catalogue de recettes

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

- **Source de données du catalogue** : choisir la source exacte pour Classic Era (export DB2 type wago.tools,
  base communautaire…) et vérifier les conditions d'utilisation. Risque : les recettes WoW Forever ne seront connues
  qu'à la sortie et au fil des découvertes → saisie manuelle au début.
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
- Composition validée / modifiée.
- Rappel avant un événement (délai configurable, ex. 1 h avant).
- Événement annulé ou modifié (date/heure).
- Nouvelle demande de craft.

**Messages privés (MP)** au joueur concerné :
- Placement dans un événement : confirmé / banc.
- Demande de craft prise en charge / livrée (pour le demandeur).
- Nouvelle demande de craft le ciblant (pour le crafteur).
- Rappel personnel avant un événement où il est confirmé.

**Commandes slash** :
- `/events` — prochains événements.
- `/inscription <événement>` — s'inscrire (perso, rôle, statut).
- `/craft <recette ou objet>` — qui sait crafter quoi.

**Préférences** : chaque joueur peut désactiver les MP (globalement ou par type) depuis son profil.

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
| Authentification | **Discord OAuth2** (flux maison : échange du code, lecture de `/users/@me` et `/users/@me/guilds`) puis émission de **JWT** via **djangorestframework-simplejwt** |
| Bot | **discord.py**, lancé par `manage.py runbot`, accès direct à l'ORM |
| Tâches de fond | Pas de Celery/Redis : boucles `discord.ext.tasks` dans le bot |
| Admin | Django admin pour les données de référence et le dépannage |

**Stratégie JWT :**
- **Access token** courte durée (~15 min), gardé **en mémoire** côté front (jamais en `localStorage`).
- **Refresh token** longue durée en **cookie `httpOnly`, `Secure`, `SameSite=Strict`**, limité au chemin `/api/auth/`,
  avec rotation et blacklist à l'usage.
- Après le callback Discord, le backend pose le cookie de refresh et redirige vers le front, qui obtient un access token
  via `/api/auth/refresh/`. Déconnexion = blacklist du refresh + suppression du cookie.
- À chaque refresh, on vérifie que le compte est toujours actif (membre désactivé = accès coupé).

**Notifications (outbox) :** le site écrit des lignes dans une table `Notification` (type, destinataire ou salon,
payload, statut) ; le bot les dépile et les envoie. Les rappels d'événements sont générés par une boucle du bot qui
scrute les événements à venir. Découplage simple : si le bot est arrêté, rien n'est perdu.

**Découpage en apps Django :**

| App | Contenu |
|---|---|
| `accounts` | Utilisateur (ID Discord, rôle site, bio, préférences de notification), disponibilités, auth Discord/JWT |
| `guild` | Paramètres de guilde (nom, faction, royaume, ID serveur et salon Discord) |
| `gamedata` | Base de données du jeu : classes, races, stats de base, objets, sets, enchantements, sorts, talents, métiers, recettes, instances ; commandes d'import et surcharges « Forever » |
| `characters` | Personnages, sets d'équipement, builds de talents, métiers des personnages, recettes connues |
| `stats` | Moteur de calcul des statistiques (sans modèle, logique pure et testée) |
| `crafting` | Demandes de craft |
| `events` | Événements, inscriptions, placements |
| `notifications` | Outbox de notifications |
| `discordbot` | Bot, commandes slash, boucles de tâches, commande `runbot` |

### Frontend

| Élément | Choix |
|---|---|
| Build | **Vite** + **React** + **TypeScript** |
| Routage | **React Router** |
| Données serveur | **TanStack Query** ; client et types **générés depuis le schéma OpenAPI** (openapi-typescript) |
| UI | **Tailwind CSS** + **shadcn/ui**, thème sombre aux couleurs WoW, couleurs de classe officielles |
| Formulaires | react-hook-form + zod |
| Calendrier | Composant calendrier à choisir à l'implémentation (ex. FullCalendar ou vue maison) |
| Spécifique WoW | Composants maison : infobulles d'objets/sorts, fenêtre d'équipement, calculateur de talents |

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
- **Secrets** en variables d'environnement (`.env` non versionné) : clés Django/JWT, client ID/secret OAuth Discord,
  token du bot, ID du serveur Discord, IDs des rôles Discord autorisés, ID Discord du premier GM.
- **Dev local** : `docker compose` pour PostgreSQL, Django en `runserver`, Vite en dev avec proxy `/api`.
- **Icônes** du jeu stockées sur un volume et servies en statique par Caddy (cache long).

### Qualité

- Backend : **pytest-django**, **ruff** (lint + format).
- Frontend : **Vitest**, **ESLint**, **Prettier**, `tsc --noEmit`.
- **CI GitHub Actions** : lint + tests back et front sur chaque push / PR.

### Points ouverts

- Nom de domaine et fournisseur du VPS.
- Création de l'application Discord (OAuth + bot) dans le Discord Developer Portal.

---

## 10. MVP et feuille de route

Principe : mettre en ligne au plus vite ce qui sert dès la sortie du jeu (qui joue quoi, sorties de groupe),
puis construire les grosses briques (base de données du jeu, fiche de personnage).

| Lot | Contenu | Sections |
|---|---|---|
| **0 — Socle** | Dépôt (backend/frontend/deploy), Docker, CI, connexion Discord + JWT avec contrôle du rôle Discord « Membre », rôles du site, paramètres de guilde, déploiement sur le VPS | 1, 2, 9 |
| **1 — Roster** | Profils, disponibilités, personnages (classe, race, niveau, rôles, main/alts), roster, synthèse de composition. Classes et races saisies à la main (sans attendre l'import complet) | 3 |
| **2 — Agenda** | Événements, inscriptions, composition validée, calendrier, bouton « Dupliquer » | 7 |
| **3 — Base de données du jeu** | Import Classic Era (objets, sets, enchantements, sorts, talents, stats de base, icônes), surcharges « Forever », encyclopédie, infobulles | 5 |
| **4 — Fiche de personnage** | Sets d'équipement, calculateur de talents et builds, projection, moteur de stats (sans talents) | 4 |
| **5 — Bot Discord** | Notifications en salon et en MP, rappels, commandes slash, révocation d'accès en temps réel | 8, 2 |
| **6 — Métiers** | Métiers des personnages, catalogue de recettes, « qui sait crafter ? », demandes de craft | 6 |

### Après le MVP (backlog)

- Prise en compte des talents dans les stats.
- Événements récurrents.
- Synchronisation des rôles du site avec les rôles Discord.
- Import automatique des personnages via l'API Blizzard (si elle couvre WoW Forever).
- Buffs / consommables dans le calcul des stats.
- Annonces, export iCal, banque de guilde, suivi du loot / DKP.
