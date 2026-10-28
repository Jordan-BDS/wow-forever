# Cahier des charges — Plateforme de guilde WoW Forever

> Document vivant, construit étape par étape. Dernière mise à jour : 2026-10-28.

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
11. [Synchronisation depuis le jeu](#11-synchronisation-depuis-le-jeu) 🚧 (addon, compagnon, fiche vivante, classements)

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
4. Les rôles autorisés sont configurés par **ID de rôle** (pas par nom, qui peut être renommé), sous forme de
   liste (ex. Membre, Officier, GM si ce sont des rôles Discord distincts). Toute la configuration Discord
   (application, token du bot, serveur, rôles autorisés, premier GM) se saisit par le GM dans **Guilde › Paramètres**,
   avec un bouton qui vérifie le serveur et liste ses rôles ; les variables d'environnement ne servent que de secours
   au premier démarrage, avant qu'un GM puisse se connecter.

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
- **Races** (avec faction) — y compris les deux **Éolides** (Skyborn), une par faction d'après le client Forever
- **Compatibilités race ↔ classe**, tirées de la table CharBaseInfo du client Forever (ex. Mort-vivant paladin, Nain chaman)
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
du jeu. Les bonus de set sont listés (actifs / inactifs selon le nombre de pièces) avec leur détail sur Wowhead ;
leurs stats ne sont pas encore additionnées.

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

Catalogue **complet** pré-rempli (import du client, cf. § 5) ; chaque joueur **coche les recettes connues** par
ses personnages, avec un bouton qui coche d'un coup toutes les recettes accessibles à son niveau de compétence (à élaguer
ensuite : les données client ne distinguent pas de façon fiable formateur, drop et vendeur).
Seules les recettes des métiers du personnage sont proposées.

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
Le crafteur peut **rendre** une demande prise en charge, qui redevient ouverte. Seul un personnage qui connaît la
recette peut la prendre ; une demande ciblée ne peut être prise que par le crafteur visé (ou un officier).

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
- **Confirmation automatique** : un inscrit « Présent » est confirmé d'office tant qu'il reste de la place
  (besoin du rôle non atteint, puis taille max). Au-delà, il reste Non placé et l'organisateur arbitre.
  « Peut-être » et « En retard » ne sont jamais confirmés d'office ; se déclarer « Absent » libère sa place.
  Un placement décidé par l'organisateur (confirmé ou banc) n'est pas remis en cause par le joueur.
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

**Synchronisation avec l'onglet « Événements » de Discord** (dans les deux sens) :
- Chaque événement planifié du site existe aussi comme événement planifié Discord (titre, début, fin, description
  suivie du lien vers la fiche, lieu = instance). Modification de date/titre/description et annulation sur le site
  se répercutent dans Discord ; la fiche du site affiche un lien vers l'événement Discord.
- Un événement créé dans l'onglet Discord par un membre ayant un compte arrive sur le site en type
  « Social / autre », son créateur comme organisateur ; ses modifications et sa suppression sont reflétées
  (suppression = annulation sur le site, l'historique reste). Un créateur sans compte est ignoré.
- Le bouton « Intéressé » de Discord n'est pas une inscription : il ne porte ni personnage ni rôle.

**Salons** : quatre réglages dans Guilde › Paramètres, choisis dans la liste des salons texte du serveur après
« Vérifier le serveur » : `#agenda` (messages d'inscription, déplacements, annulations, rappels, compositions),
`#demande-de-craft` (nouvelles demandes), `#sondages` (message de suivi de chaque sondage, rappels, résultat,
annulation) et un salon général de secours qui reçoit ce dont le salon dédié n'est pas renseigné. La commande `discord_setup_channels` crée
`#agenda` et `#demande-de-craft` en **lecture seule** pour les membres (voir, réagir, utiliser les boutons ;
pas d'écriture ni de fils), avec les droits d'écriture pour le bot, et enregistre les IDs.

**Message d'inscription dans `#agenda`** :
- À la création d'un événement, le bot publie un message avec l'état de l'événement, les inscrits par rôle
  (✅ = confirmé) et des boutons Présent / Peut-être / En retard / Absent / Me désinscrire. Il est réédité à
  chaque changement (inscription sur le site ou via les boutons, placement, date, annulation), et les boutons
  disparaissent quand les inscriptions ferment.
- Un clic inscrit le joueur avec son unique combinaison perso / rôle possible, sinon un menu éphémère lui fait
  choisir ; une inscription existante ne change que de statut.
- Le site écrit une demande `event_sync` dédupliquée dans l'outbox ; le bot la dépile et aligne Discord. Les
  échos de ses propres écritures (identiques à l'état en base) sont ignorés, ce qui évite les boucles.

**Message de suivi d'un sondage dans `#sondages`** (lecture seule) : publié à la création, il affiche la
phase en cours et ses échéances, les règles, et le classement en direct (votes et votants, 15 premières
propositions, le reste renvoie au site), puis le résultat validé. Il est réédité à chaque proposition, retrait,
vote, modification, validation ou annulation, et quand une phase se termine toute seule. Propositions et votes
se font sur le site uniquement (pas de vote par réaction) ; la fiche du sondage renvoie vers ce message.

**Autres messages dans le salon** :
- Composition publiée par l'organisateur (bouton « Publier sur Discord » sur la fiche, pour éviter un message à
  chaque placement).
- Rappel avant un événement (délai configurable, ex. 1 h avant).
- Événement annulé ou modifié (date/heure).
- Nouvelle demande de craft, titrée par le métier (ex. « Forge : 2 × Épée pour Koj »).
- Sondage : rappel 24 h avant la fin des propositions et avant la fin des votes, résultat validé, annulation
  (l'ouverture est portée par le message de suivi).

**Messages privés (MP)** au joueur concerné :
- Placement dans un événement : confirmé / banc.
- Demande de craft prise en charge / rendue par le crafteur / livrée (pour le demandeur).
- Nouvelle demande de craft le ciblant (pour le crafteur).
- Rappel personnel avant un événement où il est confirmé.

**Commandes slash** :
- `/events` — prochains événements.
- `/inscription <événement>` — s'inscrire (perso, rôle, statut).
- `/craft <recette ou objet>` — qui sait crafter quoi (livrée avec le lot 6).

**Préférences** : chaque joueur peut désactiver les MP (globalement ou par type : placement, rappels, crafts)
depuis son profil.

**Réglages** (GM, page Paramètres) : salons (agenda, crafts, sondages, général), délai de rappel avant un
événement (défaut 60 min).
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
| Statut | ✅ | `Propositions` → `Votes` → `Clos` → `Validé` (transitions automatiques aux dates, sauf la validation), ou `Annulé` |

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
sondage en cours (prolongation). Un sondage ne peut être **supprimé** qu'avant sa première proposition ; ensuite
il peut être **annulé** à tout moment avant validation : il passe en `Annulé`, reste consultable avec ses
propositions et ses votes, et aucun résultat ne sera validé. L'annulation est annoncée dans le salon des sondages.

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
| **7 — Appairage et import** | nov. 2026 | Code d'appairage, jeton de compagnon, point d'import versionné, stockage brut par personnage, mise à jour des champs du personnage, badge « synchronisé », import de secours par collage de chaîne | 11 |
| **8 — Addon** | dès le client du 4 nov. 2026 | Collecte en jeu (personnage, équipement, talents, métiers et recettes, accès, verrous, réputations), puis compteurs d'activité | 11 |
| **9 — Compagnon** | déc. 2026 | Application Tauri : appairage, dossier WoW, installation et mise à jour de l'addon embarqué, surveillance du fichier, envoi, mise à jour automatique ; release GitHub par CI ; page « Compagnon » du profil | 11 |
| **10 — Fiche vivante et classements** | — | Onglets « En jeu », comparaisons porté / planifié, progression de guilde, classements par période, récap hebdomadaire Discord | 11 |

**État au 27 octobre 2026 : les six lots sont livrés et fusionnés dans `main`.** Reste la mise en ligne (VPS,
domaine, application Discord, import des données du jeu en production) et les retours d'usage.

### Après le MVP (backlog)

- Stats dérivées et stats de base dans le moteur (points de vie, crit, toucher, esquive…), puis talents, puis
  buffs / consommables.
- Encyclopédie interne complète et infobulles maison.
- Événements récurrents.
- Synchronisation des rôles du site avec les rôles Discord.
- Import automatique des personnages via l'API Blizzard (si un espace Forever apparaît ; aucune annonce de
  Blizzard au 28 octobre 2026, cf. étape 11).
- Annonces, export iCal, banque de guilde, suivi du loot / DKP.

---

## 11. Synchronisation depuis le jeu

Faire remonter sur le site, sans saisie, tout ce que le jeu sait de chaque personnage : équipement porté, talents,
métiers et recettes connues, accès et verrous de raid, puis des **compteurs d'activité** (champs de bataille, donjons,
récoltes…) qui alimentent une fiche de personnage « vivante » et des **classements de guilde**.

### Pourquoi un addon et un compagnon

- Un addon WoW n'a **aucun accès réseau** : il ne peut qu'écrire dans un fichier `SavedVariables`, à la déconnexion
  ou au `/reload`. Il faut donc un programme sur le PC pour envoyer ce fichier.
- Raider.IO ou Warcraft Logs ne remontent rien depuis le jeu : ils lisent l'**API publique Blizzard** (profils,
  classements) et, pour les logs, un programme de bureau envoie le fichier de combat.
- Pour WoW Forever, **aucun espace d'API Blizzard n'existe ni n'est annoncé** au 28 octobre 2026 (les fils du
  forum développeurs restent sans réponse officielle ; tous les espaces essayés renvoient 403). On garde la source
  « API Blizzard » en réserve, mais le calendrier n'en dépend pas.
- Côté addon, Forever repose sur l'**architecture d'interface moderne** (base 12.1.5, interface `16001`, suffixe
  `Forever` accepté dans le `.toc`) : espaces `C_Item`, `C_Spell`, `C_TradeSkillUI`, valeurs « secrètes » en combat.
  Les anciennes fonctions globales de Classic ont disparu.

### Architecture

```
  Jeu (addon Lua) ──écrit à la déconnexion──▶ WTF/Account/<compte>/SavedVariables/WoWForeverGuilde.lua
                                                        │  surveillance du fichier
                                              Compagnon (Tauri, barre des tâches)
                                                        │  POST /api/sync/import  (jeton de compagnon)
                                              Site ── stockage brut + tables normalisées ── fiche, roster, classements
```

**Décisions (28 octobre 2026) :** compagnon en **Tauri** (interface React comme le site, noyau Rust limité à la
surveillance de fichier et aux appels HTTP, exécutable de quelques Mo, mise à jour automatique) ; connexion par
**code d'appairage** (pas d'OAuth Discord dans l'exécutable, qui devrait embarquer le secret client).

### L'addon

- Un seul fichier `SavedVariables` **au niveau du compte**, une entrée par personnage, pour que le compagnon ne
  surveille qu'un fichier et retrouve tous les persos.
- L'addon **sérialise lui-même en JSON** (chaîne dans le fichier Lua) : le compagnon n'a pas besoin d'interpréter
  du Lua. Chaque export porte une **version de format**, l'horodatage, le royaume et le nom complet (prénom + nom,
  propre à Forever).
- Collecte à l'ouverture de session et sur événements : changement d'équipement, de talents, ouverture de la fenêtre
  d'un métier (seule façon d'obtenir la liste des recettes : l'addon affiche un rappel « ouvre tes métiers une fois »
  tant qu'un métier n'a jamais été lu), fin de match PvP, entrée en instance, mort de boss, butin reçu après un sort
  de récolte, mort du personnage, quête rendue, changement de réputation ou d'honneur.
- Les **compteurs sont cumulés dans le fichier** et envoyés tels quels ; le site garde la dernière valeur, jamais une
  somme d'envois (pas de double comptage, renvoi inoffensif).
- Fenêtre en jeu minimale : état de la collecte par catégorie, bouton « Copier la chaîne d'export » (secours sans
  compagnon), interrupteurs des catégories sensibles.
- Pas d'écriture pendant un combat, pas de lecture des valeurs secrètes : l'addon ne doit jamais provoquer d'erreur.

### Le compagnon

| Écran | Contenu |
|---|---|
| Appairage | Saisie du code à 6 caractères obtenu sur le site (Profil › « Lier le compagnon »), échangé contre un jeton longue durée propre à cette machine, stocké dans le coffre du système |
| Dossier WoW | Détection automatique du dossier `_forever_` (chemins habituels, registre), confirmation ; gestion de plusieurs comptes WoW |
| Catégories | Interrupteurs par catégorie (sacs/banque/or désactivés par défaut), repris de l'addon |
| État | Dernier envoi, personnages reconnus, erreurs ; icône de barre des tâches ; démarrage avec Windows optionnel |

- Déclenchement : modification du fichier (donc à chaque déconnexion ou `/reload`), **empreinte** comparée au dernier
  envoi, envoi seulement si différent. Hors ligne : réessai au prochain changement ou au lancement.
- Distribution : GitHub Releases, mise à jour automatique Tauri. Sans certificat de signature, Windows affiche
  l'avertissement SmartScreen au premier lancement (acceptable pour la guilde ; Azure Trusted Signing en option) ;
  macOS demande un compte développeur Apple (99 $/an), à décider selon la demande.

### Distribution et installation (décisions du 28 octobre 2026)

**Un seul téléchargement pour le joueur : l'exécutable du compagnon, qui installe et met à jour l'addon.**

- **Dépôt** : `companion/` (Tauri) et `addon/WoWForeverGuilde/` (Lua) rejoignent le monorepo. Le dossier de l'addon
  est **embarqué dans l'exécutable** comme ressource à la compilation : une seule version pour les deux.
- **Compilation par GitHub Actions**, jamais sur le VPS (`make update` ne change pas) : un tag `companion-vX.Y.Z`
  déclenche la construction sur des machines Windows et macOS, la signature du mécanisme de mise à jour Tauri et
  la publication d'une **release GitHub** (exe, dmg, fichier de mise à jour, et l'addon seul en zip pour le secours).
- **Installation de l'addon par le compagnon** : au lancement, il compare la version présente dans
  `Interface/AddOns/WoWForeverGuilde/` avec la sienne et copie la bonne ; si le jeu tourne, il demande une
  reconnexion ou un `/reload`. Le joueur ne touche jamais au dossier WoW.
- **Mise à jour** : le compagnon se met à jour tout seul (updater Tauri sur la release GitHub) puis met l'addon à
  jour dans la foulée.
- **Page « Compagnon » du profil** : boutons de téléchargement Windows / macOS pointant vers la dernière release
  (version et date affichées), génération du code d'appairage, état du lien (machine, version de l'addon, dernier
  envoi), lien de secours vers l'addon seul et vers l'import par collage de chaîne.
- **Backend** : un point d'API lit la dernière release GitHub (cache d'une heure) pour la page et pour signaler
  un compagnon trop ancien à l'import.
- **Limites acceptées** : avertissement SmartScreen au premier lancement sans certificat (les mises à jour
  suivantes passent grâce à la signature Tauri) ; macOS exige un clic droit « Ouvrir » sans compte développeur ;
  détection du dossier WoW pour les installations standard, choix manuel sinon.

### Format d'échange et transfert

**Un seul format, deux chemins.** L'addon produit un **code d'export** ; le compagnon ne fait que le transmettre, le
joueur sans compagnon le colle lui-même. Mêmes octets, même point d'entrée, même traitement.

- **Production** : à la déconnexion ou au `/reload`, l'addon sérialise sa table en **JSON** (encodeur maison, WoW
  n'a pas de bibliothèque JSON), compresse avec **LibDeflate** et encode en **texte imprimable** (alphabet de 64
  caractères : +33 % contre +100 % pour l'hexadécimal). Le code est écrit dans `SavedVariables` et affiché dans la
  fenêtre « Exporter » de l'addon (texte présélectionné, Ctrl+C ; un addon ne peut pas écrire le presse-papiers).
- **Anatomie** : préfixe `WFG<version>:`, données, somme de contrôle (détecte un code tronqué à la copie). Une version
  inconnue est refusée proprement (« mets à jour l'addon »).
- **Taille** : 10 à 20 Ko de JSON par personnage 60 (300 recettes, équipement, talents, compteurs), 3 à 5 Ko
  compressés, 4 à 7 Ko de texte ; cinq personnages ≈ 35 Ko. Taille maximale acceptée par le site : 256 Ko.
- **Contenu par personnage** : identité (prénom, nom, royaume, classe, race, niveau, date d'export, temps de jeu et
  or si partagés) ; équipement par emplacement (identifiant d'objet et d'enchantement) ; talents (rang par
  identifiant) ; métiers (identifiant, compétence, maximum, spécialisation, identifiants des recettes connues) ;
  réputations ; quêtes d'accès ; verrous (réinitialisation, boss tombés) ; PvP (victoires honorables à vie, rang,
  joués / gagnés par champ de bataille) ; compteurs cumulés (boss par identifiant avec premier et dernier kill,
  donjons terminés, morts, quêtes rendues, récoltes par objet, fabrications par recette) et date de début de
  comptage. **Des identifiants, jamais des libellés** : les noms viennent de l'index du jeu (étape 5), quelle que soit
  la langue du client.
- **Compagnon** : extrait le code du fichier `SavedVariables` par recherche de texte (aucune interprétation du Lua),
  compare son empreinte à celle du dernier envoi, envoie tel quel avec son jeton.
- **Traitement côté site** (identique pour les deux chemins) : authentification (session ou jeton) → décodage,
  décompression, validation par version → rejet d'une empreinte déjà importée → rattachement par prénom + nom +
  royaume aux personnages du compte (inconnu : proposition de création ; jamais vers un autre joueur ; export plus
  ancien que le dernier import ignoré) → mise à jour des tables normalisées et archivage de l'export brut comme
  instantané du jour → réponse « 3 personnages mis à jour, 1 inconnu, 12 nouvelles recettes », affichée sur la page
  de collage comme dans le compagnon.
- **Répartition des responsabilités** : seul l'addon connaît le jeu, seul le site connaît le format, le compagnon est
  trivial et interchangeable. Un changement d'API Lua ne touche que l'addon.

### Appairage et import côté site

- **Jeton de compagnon** : créé par l'échange du code, révocable depuis le profil (liste des machines liées, dernier
  envoi), limité au point d'import. Le code expire après 10 minutes ou dès son usage.
- **Point d'import** `POST /api/sync/import` : accepte un export complet ; vérifie la version du format (refus propre
  d'une version inconnue), **rattache chaque personnage à un personnage du compte** (par nom complet + royaume ;
  proposition de création si inconnu, jamais rattachement à un perso d'un autre joueur), rejette les horodatages plus
  anciens que le dernier import.
- **Import de secours** : la même chaîne collée dans Profil › « Importer depuis le jeu », pour qui ne veut pas du
  compagnon. Même point d'import, même traitement.
- **Stockage** : l'export brut est conservé tel quel par personnage (historique borné, ex. un instantané par jour sur
  90 jours), ce qui permet d'exploiter plus tard des données non encore affichées ; les tables normalisées portent
  ce que le site affiche (équipement porté relié à l'index, recettes connues reliées au catalogue, talents, métiers,
  compteurs, accès, verrous, réputations).
- **Règle de priorité** : un champ importé remplace la saisie manuelle (niveau, spécialisation, métiers, recettes) ;
  les champs sans équivalent en jeu (rôles, note, main) restent manuels. La source du personnage passe à `addon`.

### Rattachement des personnages

Clé de rattachement : **prénom + nom + royaume**. Quand elle ne trouve rien :

| Situation | Comportement |
|---|---|
| Aucun personnage du joueur ne correspond | **Création directe** depuis le code (classe, race, niveau, métiers), source `addon`. Les rôles tank / heal / DPS n'existent pas en jeu : rôle par défaut déduit de la spécialisation du build en jeu, bandeau « rôles à confirmer » jusqu'à validation par le joueur |
| Nom différent mais un candidat plausible existe (même classe, même race, jamais synchronisé) | **Proposition de fusion**, jamais automatique : « “Thrall” sur le site est-il “Thrall Fils-de-Durotan” en jeu ? Fusionner / Créer un nouveau personnage ». Par collage : question dans l'écran de résultat ; par compagnon : personnage importé **en attente**, « 1 personnage à rattacher » dans le compagnon et sur le profil. Le lien est mémorisé ensuite |
| Le nom correspond au personnage d'un **autre joueur** | Refus, rien n'est importé, officiers prévenus (noms uniques par région sur Forever : compte partagé ou erreur à régler à la main) |
| Personnage que le joueur ne veut pas sur le site (alt banque…) | « Ignorer ce personnage » mémorisé dans l'écran de résultat ; désactivation possible aussi depuis l'addon |
| Personnage du site absent du code | Inchangé, saisie manuelle conservée, badge « jamais synchronisé » |

Prérequis de modèle : les noms Forever sont en **deux parties** ; le personnage gagne un champ *nom de famille*
(le roster affiche le prénom, nom complet au survol et sur la fiche).

### Données collectées

| Catégorie | Contenu | Fiabilité | Par défaut |
|---|---|---|---|
| Identité | Nom complet, royaume, classe, race, niveau, temps de jeu, or | Exacte (jeu) ; or et temps de jeu opt-in | ✅ (or ❌) |
| Équipement | 19 emplacements : objet, enchantement, qualité, niveau d'objet | Exacte | ✅ |
| Talents | Points par talent, ordre non connu (le build « en jeu » est figé) | Exacte | ✅ |
| Métiers | Compétence, spécialisation, **recettes connues** | Exacte quand la fenêtre a été ouverte | ✅ |
| Accès et verrous | Quêtes d'accès aux raids, verrous en cours et date d'expiration | Exacte | ✅ |
| Réputations | Factions et niveaux | Exacte | ✅ |
| PvP | **Victoires honorables à vie** et rang (totaux du jeu) ; champs de bataille joués / gagnés / perdus par type | Totaux exacts ; BG comptés depuis l'installation | ✅ |
| PvE | Donjons et raids entrés / terminés (dernier boss), boss tués par nom et date, morts | Comptés depuis l'installation | ✅ |
| Récolte et artisanat | Minerais, herbes, peaux, poissons ramassés ; objets fabriqués par recette | Approximatif (sort de récolte + butin suivant) | ✅ |
| Quêtes | Quêtes rendues (nombre), quêtes clés marquées | Comptées depuis l'installation ; clés exactes | ✅ |
| Sacs et banque | Matériaux de craft en stock | Exacte | ❌ opt-in |

Les compteurs « depuis l'installation » sont toujours affichés avec la date de début de comptage. Les kills PvP
détaillés par adversaire dépendent du journal de combat, en partie secret sur Forever : à vérifier en jeu.

### Fiche de personnage vivante

La fiche de l'étape 4 reste la fiche de **préparation** (sets planifiés, builds, projection). L'import ajoute la
réalité du jeu à côté, sans la remplacer.

- **En-tête** : nom complet, classe colorée, race, niveau, spécialisation déduite, main/alt, et le badge de
  fraîcheur : « Synchronisé depuis le jeu il y a 2 h » (vert), « il y a 9 jours » (orange), « saisie manuelle »
  (gris). Au survol : date exacte, machine, catégories reçues.
- **Onglet Équipement** : un set système **« Porté en jeu »**, en lecture seule, s'ajoute aux sets planifiés et sert
  de référence. Vue **comparaison** entre le set porté et un set planifié : par emplacement, identique / différent /
  manquant, avec la différence de stats brutes (moteur de l'étape 4). C'est la « liste de courses » du joueur.
- **Onglet Talents** : build **« En jeu »** en lecture seule à côté des builds planifiés ; comparaison avec le build
  actif, points différents surlignés. Le build en jeu devient la source de la spécialisation du roster.
- **Onglet Métiers** : compétence réelle, recettes connues filtrables (lien direct « demander ce craft »), et
  **recettes manquantes** par rapport au catalogue, triées par source (raid, réputation, vendeur, drop).
- **Onglet Progression** : accès aux raids en pastilles (acquis / manquant), verrous en cours avec compte à
  rebours, réputations en barres, honneur et rang, puis les compteurs : BG joués et gagnés avec taux de victoire,
  donjons et raids terminés, boss tués (tableau boss × nombre × dernière date), morts, récoltes par type.
- **Onglet Historique** : courbe du niveau, courbes des compteurs (une par catégorie, période choisie), journal des
  synchronisations. Les instantanés quotidiens conservés 90 jours alimentent ces courbes.
- **Fiche joueur** : totaux de tous ses personnages, dernier perso joué, temps de jeu cumulé si partagé.
- **Roster** : colonne « synchro » (pastille de fraîcheur), tri par niveau réel, filtre « a l'accès à <raid> »,
  « verrouillé cette semaine ».

### Classements

Page **Classements** dans la navigation principale, plus un widget « Cette semaine » sur l'accueil.

- **Périodes** : semaine (lundi 00:00 Europe/Paris, cohérente avec la réinitialisation des raids), mois, saison
  (depuis la sortie du jeu), total. Les classements par période se calculent par **différence entre instantanés**,
  d'où l'importance de l'historique.
- **Vue par joueur par défaut** (somme de ses personnages), bascule « par personnage ».
- **Catégories** et tableaux :
  - *PvE* : boss tués, donjons terminés, raids terminés, morts (le « classement de la honte », assumé).
  - *PvP* : victoires honorables (gain sur la période), champs de bataille gagnés, taux de victoire (minimum 10 BG).
  - *Récolte* : minerais, herbes, peaux, poissons ; un classement par ressource et un total.
  - *Artisanat* : objets fabriqués, et **demandes de craft livrées** (donnée du site, déjà disponible).
  - *Guilde* : présence aux événements (inscrit présent / organisé, donnée du site), quêtes rendues.
  - *Opt-in* : or, temps de jeu, affichés seulement pour ceux qui l'ont activé.
- **Tableau** : podium des trois premiers, top 10, puis **ta ligne** mise en évidence avec ton rang même hors
  top 10 ; variation par rapport à la période précédente (▲ ▼) ; clic vers la fiche du personnage.
- **Titres de la semaine** attribués automatiquement le lundi (« Mineur de la semaine », « Boucher des BG »,
  « Mort le plus souvent »…), affichés sur la fiche du gagnant pendant la semaine, et **récapitulatif hebdomadaire**
  posté par le bot dans le salon général (top 3 par catégorie, nouveaux accès, premiers kills).
- **Progression de guilde** : page par raid, chaque boss avec la **date du premier kill de la guilde** (dérivée des
  événements de boss horodatés, boss par un groupe de la guilde = au moins 5 joueurs du site présents), nombre de
  kills, et le pourcentage de membres niveau 60 ayant l'accès. Répartition des niveaux du roster dans le temps.
- **Équité** : les compteurs ne comptent qu'avec l'addon installé ; chaque tableau indique « depuis le JJ/MM »
  pour les joueurs arrivés en cours de période. Un joueur peut se retirer d'une catégorie depuis son profil.

### Confidentialité et confiance

- Les données viennent du client du joueur : elles ne sont pas vérifiables et ne servent qu'à la vie de la guilde
  (pas de classement public). Le GM peut **remettre à zéro** les compteurs d'un personnage en cas d'anomalie.
- Catégories sensibles (or, sacs, banque, temps de jeu) désactivées par défaut, activables par le joueur dans
  l'addon ou le compagnon, et masquables des classements.
- Suppression d'un personnage ou du compte : exports bruts et compteurs supprimés avec.

### Points ouverts

- API Lua exacte de Forever à la sortie (bêta fermée le 21 octobre 2026) : noms d'événements PvP, détection de
  fin de donjon, fonctions de métiers ; valider les collectes une par une sur le client du 4 novembre.
- Reconnaissance des boss et des derniers boss d'instance : table d'instances de l'étape 7 à compléter avec les
  identifiants de rencontre.
- Signature de l'exécutable Windows et distribution macOS : selon le nombre de joueurs concernés.
- Si un espace d'API Blizzard apparaît : import de la partie identité / équipement / talents sans compagnon, en
  complément de l'addon pour le reste.
