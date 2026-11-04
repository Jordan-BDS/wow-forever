# WoW Forever Guilde — addon

Collecte la progression du personnage et produit un code d'export pour le site de la guilde. Ne touche jamais au
réseau : le client écrit `WoWForeverGuildeDB` à la déconnexion et au `/reload`, le compagnon (ou un copier-coller)
transporte le code jusqu'au site.

- `Core.lua` : cycle de vie, bus d'événements, protection des collecteurs (`pcall`, hors combat), `/wfg`.
- `Store.lua`, `Journal.lua`, `Export.lua`, `Json.lua`, `Base64.lua` : base, journal quotidien, code `WFG1:…`.
- `Collectors/` : un module par catégorie (identité, équipement, talents, métiers, réputations, accès, verrous, PvP,
  PvE, créatures tuées, récolte et artisanat, quêtes, annonces de mort). Les créatures tuées (`Collectors/Kills.lua`)
  viennent du journal de combat : toute créature frappée par moi ou mes unités (familier, totems) dans les 15 s
  avant sa mort, ou dont j'ai porté le coup fatal ; compteur cumulé `kills` dans le journal quotidien, détail par
  identifiant de PNJ (nom, nombre, premier et dernier kill) dans `char.mobs`, hors journal, 500 espèces au plus.
- `Data.lua` : tables de référence à tenir à jour (quêtes d'accès, derniers boss, sorts de récolte).
- `Phrases.lua` : gabarits des annonces de mort (liste à fournir par Jordan).
- `UI.lua` : fenêtre principale, export, dialogues, texte flottant des morts.
- `Positions.lua`, `MapUI.lua` : partage de position. Case « Partager ma position » (cochée par défaut) : le client
  émet carte, coordonnées, niveau et résumé de talents par message addon (préfixe `WFG`, canal de guilde, ou canal
  caché tant que la guilde n'existe pas) au changement de zone, au déplacement et toutes les 60 s ; les autres
  apparaissent en points couleur de classe sur la carte du monde (HereBeDragons-Pins : zone, continent, monde).
  Survol : nom, niveau, zone, talents, âge ; clic gauche : menu Inviter (ou Suggérer l'invitation quand on n'est
  pas chef) / Chuchoter. Ne pas partager = ne pas voir. Un membre silencieux depuis 3 min disparaît. Points aussi
  sur la minimap (flottant au bord vers les membres proches), réglage à part. Recherche de groupe (`/wfg lfg texte`
  ou le champ de la liste) diffusée avec la position. Appel à l'aide : détecté dans le journal de combat (joueur
  hostile qui me frappe, hors instance et hors duel) ou `/wfg sos`, un envoi par minute ; chez les autres, toast et
  son dans la même zone, ligne de chat ailleurs, anneau rouge sur le point 2 min.
- `RosterUI.lua` : liste « Guilde en jeu » (`/wfg qui`) : membres en ligne par zone d'après le roster de guilde (même
  sans addon), enrichis des positions reçues ; section « Cherchent un groupe » ; clic → même menu que la carte.
- `Libs/` : LibStub, LibDeflate (export), CallbackHandler-1.0 et HereBeDragons-2.0 (+ Pins) pour la carte ;
  HereBeDragons connaît le client Forever (`WOW_PROJECT_CAMELOT`).

Tests : `cd backend && uv run pytest apps/gamesync/test_addon.py` (environnement WoW simulé, Lua 5.1 via lupa).
