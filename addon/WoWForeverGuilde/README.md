# WoW Forever Guilde — addon

Collecte la progression du personnage et produit un code d'export pour le site de la guilde. Ne touche jamais au
réseau : le client écrit `WoWForeverGuildeDB` à la déconnexion et au `/reload`, le compagnon (ou un copier-coller)
transporte le code jusqu'au site.

- `Core.lua` : cycle de vie, bus d'événements, protection des collecteurs (`pcall`, hors combat), `/wfg`.
- `Store.lua`, `Journal.lua`, `Export.lua`, `Json.lua`, `Base64.lua` : base, journal quotidien, code `WFG1:…`.
- `Collectors/` : un module par catégorie (identité, équipement, talents, métiers, réputations, accès, verrous, PvP,
  PvE, récolte et artisanat, quêtes, annonces de mort).
- `Data.lua` : tables de référence à tenir à jour (quêtes d'accès, derniers boss, sorts de récolte).
- `Phrases.lua` : gabarits des annonces de mort (liste à fournir par Jordan).
- `UI.lua` : fenêtre principale, export, dialogues, texte flottant des morts.
- `Positions.lua`, `MapUI.lua` : partage de position. Case « Partager ma position » (cochée par défaut) : le client
  émet carte, coordonnées, niveau et résumé de talents par message addon (préfixe `WFG`, canal de guilde, ou canal
  caché tant que la guilde n'existe pas) au changement de zone, au déplacement et toutes les 60 s ; les autres
  apparaissent en points couleur de classe sur la carte du monde (HereBeDragons-Pins : zone, continent, monde).
  Survol : nom, niveau, zone, talents, âge ; clic gauche : menu Inviter (ou Suggérer l'invitation quand on n'est
  pas chef) / Chuchoter. Ne pas partager = ne pas voir. Un membre silencieux depuis 3 min disparaît.
- `Libs/` : LibStub, LibDeflate (export), CallbackHandler-1.0 et HereBeDragons-2.0 (+ Pins) pour la carte ;
  HereBeDragons connaît le client Forever (`WOW_PROJECT_CAMELOT`).

Tests : `cd backend && uv run pytest apps/gamesync/test_addon.py` (environnement WoW simulé, Lua 5.1 via lupa).
