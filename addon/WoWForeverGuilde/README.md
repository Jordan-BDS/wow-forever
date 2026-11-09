# Manuel Feralas — addon (dossier `WoWForeverGuilde`)

Collecte la progression du personnage et produit un code d'export pour le site de la guilde. Ne touche jamais au
réseau : le client écrit `WoWForeverGuildeDB` à la déconnexion et au `/reload`, le compagnon (ou un copier-coller)
transporte le code jusqu'au site.

- `Core.lua` : cycle de vie, bus d'événements, protection des collecteurs (`pcall`, hors combat), `/mf`. `/mf api` :
  diagnostic des API du client (talents, métiers, carte, messages addon) et de ce que les collecteurs en lisent,
  affiché dans le chat et noté avec les erreurs pour le GM (« Tests en jeu » sur le site). `/mf trace` : pendant 2 min, chaque
  message addon envoyé ou reçu s'affiche (type, expéditeur, réponse du jeu, raison d'un rejet).
- `Store.lua`, `Journal.lua`, `Export.lua`, `Json.lua`, `Base64.lua` : base, journal quotidien, code `WFG1:…`.
- `Collectors/Talents.lua` : trois lectures essayées dans l'ordre, l'API Classic (`GetTalentInfo` en valeurs), sa
  forme en table (`C_SpecializationInfo.GetTalentInfo`, Classic Era 1.15+) puis les traits modernes (`C_Traits`,
  rang par sort) ; export `grid` (« arbre-rangée-colonne » → rang, ce que le site lit en premier), `points`
  (« arbre-index », ancien format) ou `spells` (« sort » → rang). Aucune API : « Indisponible », noté une fois dans
  `/mf erreurs`.
- `Collectors/Professions.lua` : compétence dès la connexion, recettes à l'ouverture de la fenêtre ; la ligne de
  compétence est ramenée à sa ligne mère (Alchimie 171 plutôt qu'« Alchimie Classic ») via
  `C_TradeSkillUI.GetProfessionInfoBySkillLineID`, la compétence vient de la ligne d'extension quand la mère dit 0.
- `Collectors/` : un module par catégorie (identité, équipement, talents, métiers, réputations, accès, verrous, PvP,
  PvE, créatures tuées, récolte et artisanat, quêtes, annonces de mort par message addon sur le canal de guilde). Les créatures tuées (`Collectors/Kills.lua`)
  viennent du message d'expérience « X meurt, vous gagnez N points » (Forever interdit le journal de combat aux
  addons) ; compteur cumulé `kills` et nombre par créature (`counters.mobs`, clé = nom) dans le journal quotidien
  (d'où les classements hebdo par créature), premier / dernier kill dans `char.mobs`, hors journal, 500 espèces au
  plus ; rien au niveau maximum.
- `Data.lua` : tables de référence à tenir à jour (quêtes d'accès, derniers boss, sorts de récolte).
- `Samwise.blp` : icône de la guilde (portrait de Samwise Didier, l'ancienne icône « Temp » des clients Classic),
  en tête des fenêtres et dans la liste des addons (`## IconTexture`).
- `Phrases.lua` : gabarits des annonces de mort (liste à fournir par Jordan).
- `UI.lua` : fenêtre principale, export, dialogues, texte flottant des morts.
- `Positions.lua`, `MapUI.lua` : partage de position. Case « Partager ma position » (cochée par défaut) : le client
  émet carte, coordonnées, niveau et résumé de talents par message addon (préfixe `WFG`, canal de guilde ; le client
  moderne interdit les canaux de chat aux addons, donc rien ne circule sans guilde) au changement de zone, au déplacement et toutes les 60 s ; les autres
  apparaissent en points couleur de classe sur la carte du monde (HereBeDragons-Pins : zone, continent, monde).
  Survol : nom, niveau, zone, talents, âge ; clic gauche : menu Inviter (ou Suggérer l'invitation quand on n'est
  pas chef) / Chuchoter. Ne pas partager = ne pas voir. Un membre silencieux depuis 3 min disparaît. Points aussi
  sur la minimap (flottant au bord vers les membres proches), réglage à part. Recherche de groupe (`/mf lfg texte`
  ou le champ de la liste) diffusée avec la position. Appel à l'aide : **manuel seulement** (bouton dans `/mf` et
  dans la liste, ou `/mf sos` ; la cible est nommée si c'est un joueur), jamais automatique pour ne pas spammer en
  zone contestée ; un envoi par minute ; chez les autres, toast et son dans la même zone, ligne de chat ailleurs,
  anneau rouge sur le point 2 min.
- `Wanted.lua`, `WantedUI.lua` : têtes mises à prix (lot 1, 0.5.0). Un joueur adverse qui tue un membre prend un point
  de prime, jamais remis à zéro ; le tableau (`db.wanted`, niveau compte) se nourrit des messages « D » reçus, la
  sienne comprise (l'écho du jeu est reconnu comme doublon : même victime, même heure). La ligne « D » porte depuis la
  0.5.0 cinq champs de plus, ignorés par les anciennes versions : tueur joueur (lu au ciblage par `UnitIsPlayer`), sa
  classe, carte, x, y du mort. Chez les autres : l'avis de décès porte la prime (en-tête « WANTED », pied « prime N »),
  une ligne de chat, et une **tête de mort rouge** (8e marqueur de raid, prime en chiffre) sur la carte et la minimap
  là où il a frappé, qui pâlit puis disparaît après 5 min. Fenêtre `/mf wanted` (bouton dans `/mf`) : ennemis par
  prime décroissante, dernière victime, lieu, âge ; survol : la même infobulle que sur la carte. Réglage « Alertes
  Wanted ». **Kills par la guilde** (lot 2, 0.6.0) : le journal de combat étant interdit, c'est le **message de chat de
  victoire honorable** (`CHAT_MSG_COMBAT_HONOR_GAIN`, motif construit depuis `COMBATLOG_HONORGAIN` et sa variante sans
  rang, affiché par `/mf api`) qui nomme le joueur abattu ; tout le groupe le reçoit (crédit de groupe). Chaque kill de
  joueur est un événement `pk` du journal avec la prime encaissée (compteurs `pk` et `bounty`, d'où les chasseurs de
  primes du site) ; si l'ennemi est recherché (nom exact, ou prénom seul s'il est unique au tableau) : kill au tableau
  (dédoublonné à la minute par ennemi : coéquipiers, écho), message « K » aux guildiens, toast or « Prime encaissée »
  avec une phrase troll (`Phrases.lua`, `{chasseur}`, `{ennemi}`, `{prime}`, `{zone}`), tête de mort déplacée là où il
  est tombé. **Poignée de main « W »** : 8 s après la connexion on demande le tableau ; un membre répond avec un résumé
  (nom, classe, prime, kills, dernière position ; lignes de 255 octets, 40 ennemis au plus) après un délai aléatoire
  de 1 à 6 s, sauf si quelqu'un a déjà répondu ; le receveur garde le maximum de chaque valeur. À venir : tableau et
  Roxor « Chasseur de primes » sur le site (lot 3).
- `RosterUI.lua` : liste « Guilde en jeu » (`/mf qui`) : membres en ligne par zone d'après le roster de guilde (même
  sans addon), enrichis des positions reçues ; section « Cherchent un groupe » ; clic → même menu que la carte.
- `Libs/` : LibStub, LibDeflate (export), CallbackHandler-1.0 et HereBeDragons-2.0 (+ Pins) pour la carte ;
  HereBeDragons connaît le client Forever (`WOW_PROJECT_CAMELOT`).

Tests : `cd backend && uv run pytest apps/gamesync/test_addon.py` (environnement WoW simulé, Lua 5.1 via lupa).
