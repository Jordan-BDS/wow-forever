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
- `Collectors/Gathering.lua` : récolte (sort puis butin dans la fenêtre : 10 s, 30 s pour la pêche) et fabrications.
  La pêche, canalisée, est lue à `UNIT_SPELLCAST_CHANNEL_START` comme à `SUCCEEDED`, reconnue par identifiant ou par
  nom (`C_Spell.GetSpellName` ou `GetSpellInfo`, exact ou approché), et la fin de canalisation rouvre 10 s pour le
  butin ; `/mf api` montre le dernier sort lu et ce qu'il est devenu, `/mf trace` les butins comptés ou refusés.
- `Data.lua` : tables de référence à tenir à jour (quêtes d'accès, derniers boss, sorts de récolte).
- `Samwise.blp` : icône de la guilde (portrait de Samwise Didier, l'ancienne icône « Temp » des clients Classic),
  en tête des fenêtres et dans la liste des addons (`## IconTexture`).
- `Phrases.lua` : gabarits des popups (avis de décès, victoires honorables, primes encaissées) et leur remplissage
  (« de » et « à » contractés ou élidés devant le nom, pluriel des kills à plusieurs, majuscules) ; comment écrire
  un gabarit est dit en tête du fichier.
- `UI.lua` : la fenêtre `/mf` et ses onglets (un seul cadre ; chaque écran déclare le sien avec `UI.AddTab`, son
  panneau n'est construit qu'à la première ouverture ; position et dernier onglet retenus ; à droite du titre, le
  temps sans sauvegarde et le bouton Sauvegarder). Onglet Collecte (`/mf collecte`) : personnages du compte, état
  de la collecte, et le code d'export en seconde vue (`/mf export` ou le bouton). Onglet Réglages
  (`/mf reglages`) : toutes les cases, en trois groupes (carte et position, morts et popups, site et données),
  dont le rappel de sauvegarde. Onglet Nouveautés (`/mf nouveautes`) : les notes de version (`ns.CHANGELOG`,
  dans `Locales/frFR.lua`, à compléter à chaque version : un test refuse une version sans notes), en vert et
  annoncées à la connexion tant qu'elles ne sont pas lues (`settings.changelogSeen`). Onglet Diagnostic
  (`/mf diag`) : les lignes de `/mf api` et de `/mf erreurs` dans une zone à copier, boutons Relire, Noter pour le
  GM et Tracer. Listes en colonnes (`UI.MakeColumnHeaders`, `UI.MakeRow`, `UI.FillRow`) pour Guilde en jeu et
  Wanted : `Lines()` rend, en plus du texte, une valeur par colonne. Bouton de la minimap, fait à la main (clic :
  la fenêtre ; clic droit : les réglages ; glissé : il tourne autour de la minimap, angle retenu ; case des
  réglages pour le retirer). Dialogues, texte flottant des morts. `RosterUI.lua` et `WantedUI.lua` sont les
  onglets Guilde en jeu (`/mf qui`) et Wanted (`/mf wanted`).
- `Positions.lua`, `MapUI.lua` : partage de position. Case « Partager ma position » (cochée par défaut) : le client
  émet carte, coordonnées, niveau et résumé de talents par message addon (préfixe `WFG`, canal de guilde ; le client
  moderne interdit les canaux de chat aux addons, donc rien ne circule sans guilde) au changement de zone, au déplacement et toutes les 60 s ; les autres
  apparaissent en points couleur de classe sur la carte du monde (HereBeDragons-Pins : zone, continent, monde).
  Survol : nom, niveau, zone, talents, âge ; clic gauche : menu Inviter (ou Suggérer l'invitation quand on n'est
  pas chef) / Chuchoter. Ne pas partager = ne pas voir. Un membre silencieux depuis 3 min disparaît. Points aussi
  sur la minimap (flottant au bord vers les membres proches), réglage à part. Recherche de groupe (`/mf lfg texte`
  ou le champ de la liste) diffusée avec la position. Appel à l'aide : **manuel seulement** (bouton de l'onglet Guilde en jeu, et
  dans la liste, ou `/mf sos` ; la cible est nommée si c'est un joueur), jamais automatique pour ne pas spammer en
  zone contestée ; un envoi par minute ; chez les autres, toast et son dans la même zone, ligne de chat ailleurs,
  anneau rouge sur le point 2 min. La ligne « P » porte la version de l'addon (0.6.6) : une version plus récente
  vue chez un guildien donne une ligne de chat puis, hors combat et hors instance, le popup « Recharger (/reload) »,
  une fois par version et par session. Après la 0.6.13 : il faut deux guildiens plus récents (une version de
  développement en jeu ne dérange personne) ; le rechargement accepté est retenu (`db.upgradeTried`), et s'il n'a
  rien changé l'addon le dit, repropose une seule fois un quart d'heure plus tard, puis n'insiste plus pour cette
  version ; la version vient de `CODE_VERSION` (`Core.lua`) et non du `.toc`, que le client ne relit qu'à son
  lancement : après une mise à jour copiée jeu ouvert, l'addon dit de relancer le jeu au lieu de se croire en retard.
- `Wanted.lua`, `WantedUI.lua` : têtes mises à prix (lot 1, 0.5.0). Un joueur adverse qui tue un membre prend un point
  de prime ; abattu par la guilde, sa prime est encaissée et retombe à zéro, il quitte le tableau jusqu'à sa
  prochaine victime (0.6.10 ; avant, jamais remise à zéro) ; le tableau (`db.wanted`, niveau compte) se nourrit des messages « D » reçus, la
  sienne comprise (l'écho du jeu est reconnu comme doublon : même victime, même heure). La ligne « D » porte depuis la
  0.5.0 cinq champs de plus, ignorés par les anciennes versions : tueur joueur, sa classe, carte, x, y du mort.
  Joueur ou créature (`UnitIsPlayer`, secret en combat) se lit sur la cible ou le souvenir qui porte le nom du tueur,
  sinon parmi les joueurs hostiles lus dans les 10 dernières minutes (cible, survol, plaques de nom), sinon sur les
  unités encore autour une fois mort (0.6.3 ; `/mf api` dit d'où vient la réponse). Chez les autres : toute mort
  PvP est un avis « WANTED » (pied « mort en PvP », tueur coloré à sa classe, même phrase qu'en PvE) ; avec
  les alertes Wanted, l'avis porte la prime (pied « prime de N points sur X »). Le pied d'un avis donne les faits,
  chacun seulement s'il est connu : niveau, classe, lieu (0.6.13). En champ de bataille ou en arène
  (0.6.3) : ni annonce de mort, ni point, ni prime ; le kill compte dans « Joueurs abattus » (événement `pk` marqué
  `bg`, que le site ignore pour le tableau). L'avis porte aussi
  une ligne de chat, et une **tête de mort rouge** (8e marqueur de raid, prime en chiffre) sur la carte et la minimap
  là où il a frappé, qui pâlit puis disparaît après 5 min. Onglet Wanted (`/mf wanted`) : ennemis par
  prime décroissante, dernière victime, lieu, âge ; survol : la même infobulle que sur la carte. Réglage « Alertes
  Wanted ». **Kills par la guilde** (lot 2, 0.6.0) : le journal de combat étant interdit, c'est le **message de chat de
  victoire honorable** (`CHAT_MSG_COMBAT_HONOR_GAIN`) qui nomme le joueur abattu ; tout le groupe le reçoit (crédit de
  groupe). Le motif est construit depuis toutes les chaînes `COMBATLOG_HONORGAIN*` du client (nom en tête, texte
  jusqu'au marqueur suivant, quel qu'il soit), avec les chaînes des clients classique et 12.0 en secours ; les codes
  d'affichage (lien de joueur, couleur) sont retirés, et un message d'une forme inconnue qui nomme un seul ennemi du
  tableau compte quand même (0.6.4). Filet (0.6.4) : quand le compteur de victoires honorables du client bouge
  (`PLAYER_PVP_KILLS_CHANGED`, `GetPVPLifetimeStats`) sans message reconnu dans les 3 s, le kill compte, nommé d'après
  le joueur adverse mort regardé (cible, survol, focus) si son nom est lisible, sans nom sinon (compteur et
  événement `pk`, pas de Wanted). `/mf api` affiche la chaîne, les motifs, le dernier message reçu et ce qu'on en a
  tiré (« motif », « recherché », « compteur », « cadavre » ou « aucun joueur reconnu »), et le compteur lu. Second
  filet (0.6.5) : mon adversaire ciblé, vu vivant dans les 10 dernières minutes, est un cadavre (lu à la santé de la
  cible, au changement de cible, à la fin du combat) sans kill lu dans les 3 s : le kill compte à son nom, un même
  cadavre une fois ; deux pistes pour un même nom dans la fenêtre ne comptent qu'une fois. `/mf prime <nom>` joue le
  popup pour un nom du tableau sans rien enregistrer, et dit si le nom n'y est pas. Victoire honorable sur un
  joueur qui n'est pas recherché (0.6.6) : message « H » aux guildiens et popup vert « Victoire honorable » chez
  tous, hors champ de bataille et arène, avec une phrase de son propre lot (`KILL_PHRASES`, 0.6.13 : les chasseurs
  en sont le sujet ; le pied dit où), sans son, un seul popup par
  kill (écho et répétition du même chasseur ; un coéquipier qui annonce le même kill dans les 15 s ajoute son nom
  au popup déjà affiché, la phrase passe au pluriel, 5 noms au plus ; le même joueur retué plus tard a son popup,
  0.6.8 ; un popup reste 4 s au moins, le suivant attend son tour), gouverné par « Afficher les morts des autres » ; si la victime est
  recherchée chez celui qui reçoit, c'est une prime encaissée. Envoi tenace du « K » et du « H » (0.6.7) : refusé
  par le jeu, il est retenté toutes les 5 s ; parti en combat, il est répété une fois à la sortie du combat ; plus
  rien 45 s après le kill ; `/mf api` dit ce qu'a donné le dernier envoi et combien on en a reçu. Journal des
  kills (0.6.9) : chaque piste (message, compteur, cadavre, en combat ou non), ce qu'elle a donné (popup, « H »
  accepté ou refusé, « sans nom ») et chaque « K » ou « H » reçu, 14 lignes par session, affiché par `/mf api`
  avec les derniers popups (affiché, mis en attente, sorti de la file) et noté avec les erreurs à la déconnexion
  (où = « vh ») pour le GM. Le popup « Prime
  encaissée » s'affiche chez le chasseur et chez les guildiens qui reçoivent le « K », alertes Wanted cochées ou non
  (0.6.4 ; la case ne gouverne que la ligne de chat, la prime dans l'avis de décès et les têtes de mort). Chaque kill de
  joueur est un événement `pk` du journal avec la prime encaissée (compteurs `pk` et `bounty`, d'où les chasseurs de
  primes du site) ; si l'ennemi est recherché (nom exact, ou prénom seul s'il est unique au tableau) : kill au tableau
  (dédoublonné à la minute par ennemi : coéquipiers, écho), message « K » aux guildiens, toast or « Prime encaissée »
  avec une phrase troll (`Phrases.lua`, `{chasseur}`, `{ennemi}` ; pied « Prime de N points · lieu »), tête de mort déplacée là où il
  est tombé. **Poignée de main « W »** : 8 s après la connexion on demande le tableau ; un membre répond avec un résumé
  (nom, classe, prime, kills, dernière position ; lignes de 255 octets, 40 ennemis au plus) après un délai aléatoire
  de 1 à 6 s, sauf si quelqu'un a déjà répondu ; le receveur garde le maximum de chaque valeur. Côté site (lot 3) :
  tableau Wanted, classements « Joueurs abattus » et « Primes encaissées », Roxor « Chasseur de primes » ; le
  compagnon recopie le tableau de la guilde dans `db.wanted` au lancement, jeu fermé (maximum de chaque valeur).
- `RosterUI.lua` : liste « Guilde en jeu » (`/mf qui`) : membres en ligne par zone d'après le roster de guilde (même
  sans addon), enrichis des positions reçues ; section « Cherchent un groupe » ; clic → même menu que la carte.
- `Libs/` : LibStub, LibDeflate (export), CallbackHandler-1.0 et HereBeDragons-2.0 (+ Pins) pour la carte ;
  HereBeDragons connaît le client Forever (`WOW_PROJECT_CAMELOT`).

Tests : `cd backend && uv run pytest apps/gamesync/test_addon.py` (environnement WoW simulé, Lua 5.1 via lupa).
