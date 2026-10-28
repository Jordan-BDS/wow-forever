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

Tests : `cd backend && uv run pytest apps/gamesync/tests_addon.py` (environnement WoW simulé, Lua 5.1 via lupa).
