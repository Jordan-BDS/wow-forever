-- Wanted : têtes mises à prix. Un joueur adverse qui tue un membre (mort annoncée par message « D » avec « tueur
-- joueur ») prend un point de prime, jamais remis à zéro (décision du 9 novembre 2026). Le tableau vit au niveau du
-- compte (`db.wanted`, clé = nom en minuscules) : il se remplit avec les morts reçues pendant qu'on est connecté, la
-- sienne comprise ; l'écho de son propre message est reconnu comme un doublon (même victime, même heure). La
-- dernière position connue d'un ennemi est celle de sa victime au moment de mourir, ou celle du chasseur qui l'abat.
--
-- Lot 2 : kills par la guilde. Forever interdit le journal de combat : on lit le message de chat de victoire
-- honorable (« X meurt, victoire honorable… », CHAT_MSG_COMBAT_HONOR_GAIN), que tout le groupe reçoit (crédit de
-- groupe, décidé le 9 novembre 2026). Le motif vient des chaînes du client (toutes les variantes
-- COMBATLOG_HONORGAIN*, nom en tête), avec celles connues des clients Forever et retail en secours ; les codes
-- d'affichage (lien de joueur, couleur) sont retirés avant lecture ; un message d'une forme inconnue qui nomme un
-- seul ennemi du tableau compte quand même. Filet (0.6.4) : si le compteur de victoires honorables du personnage
-- bouge (PLAYER_PVP_KILLS_CHANGED) sans message reconnu dans les WANTED_KILL_WINDOW s, le kill compte, nommé
-- d'après le joueur mort regardé (cible, survol, focus) si son nom est lisible, sans nom sinon. Second filet
-- (0.6.5) : mon adversaire ciblé, vu vivant dans les SEEN_PLAYERS_TTL dernières secondes, est un cadavre (lu quand
-- ses valeurs sont lisibles : santé de la cible, changement de cible, fin de combat) sans kill lu dans la fenêtre :
-- le kill compte à son nom, un même cadavre une fois. `/mf api` dit ce qu'a donné le dernier message ; `/mf prime
-- <nom>` joue le popup pour un nom du tableau sans rien enregistrer (le popup marche-t-il, l'ennemi est-il connu ?).
-- Pas de message pour une cible qui ne rapporte pas d'honneur (d'où le second filet). Chaque kill de
-- joueur est un événement `pk` du journal (prime encaissée = prime de l'ennemi à ce moment, compteurs `pk` et
-- `bounty`) ; s'il est recherché, message « K » aux guildiens, popup « Prime encaissée » chez tous (alertes Wanted ou
-- non, la ligne de chat seulement avec), tête de mort déplacée.
-- Victoire honorable sur un joueur qui n'est pas recherché (0.6.6) : message « H » aux guildiens et popup « Victoire
-- honorable » chez tous (avec « Afficher les morts des autres »), une phrase du lot des avis de décès, un seul popup
-- par victime dans la fenêtre ; une prime encaissée pour la même victime le remplace.
-- Les kills d'un même ennemi à moins de WANTED_KILL_DEDUPE s ne comptent qu'une fois dans son tableau (le groupe
-- envoie autant de « K » que de chasseurs). En champ de bataille ou en arène, le kill compte (compteur `pk`, événement
-- `pk` marqué `bg`) mais ne touche pas au Wanted : ni prime, ni « K », ni toast, et le site l'ignore pour le tableau
-- (décision du 9 novembre 2026). Poignée de main « W » : à la connexion on demande le tableau ; un
-- membre répond avec un résumé (prime, kills, dernière position) après un délai aléatoire, sauf si quelqu'un l'a
-- déjà fait ; le receveur garde le maximum de chaque valeur.
local ADDON, ns = ...

local Wanted = {}
ns.Wanted = Wanted
local L = ns.L

local PREFIX = ns.Data.ADDON_PREFIX
local requestAt = nil -- heure de la dernière demande « W » reçue ou envoyée
local digestSeenAt = 0 -- heure du dernier résumé « W » reçu (quelqu'un a déjà répondu)

--- Clé d'un ennemi : son nom affiché en minuscules, espaces de bord retirés (pas de royaume sur Forever).
function Wanted.Key(name)
  return (tostring(name or ""):gsub("^%s+", ""):gsub("%s+$", "")):lower()
end

local function table_()
  local db = ns.db
  if not db then return nil end
  db.wanted = db.wanted or {}
  return db.wanted
end

function Wanted.Get(name)
  local t = table_()
  return t and t[Wanted.Key(name)] or nil
end

--- L'ennemi nommé par un message du jeu : clé exacte, sinon le seul recherché qui porte ce prénom (le message de
--- victoire honorable peut ne donner que le prénom là où le récapitulatif donnait prénom et nom, ou l'inverse).
function Wanted.Match(name)
  local exact = Wanted.Get(name)
  if exact then return exact end
  local first = Wanted.Key(name):match("^(%S+)")
  if not first then return nil end
  local found = nil
  for key, entry in pairs(table_() or {}) do
    if key:match("^(%S+)") == first then
      if found then return nil end -- deux homonymes : on ne tranche pas
      found = entry
    end
  end
  return found
end

local function myName()
  local c = ns.char
  if not c then return "?" end
  local name = c.name or "?"
  if c.surname and c.surname ~= "" then name = name .. " " .. c.surname end
  return name
end

local function here()
  if not (ns.Positions and ns.Positions.Here) then return nil end
  local ok, map, x, y = pcall(ns.Positions.Here)
  if not ok then return nil end
  return map, x, y
end

local function round4(v)
  return v and math.floor(v * 10000 + 0.5) / 10000 or nil
end

--- Garde au plus WANTED_MAX ennemis : les primes les plus faibles sautent d'abord, puis les plus anciennes.
local function cap(t)
  local keys = {}
  for key in pairs(t) do keys[#keys + 1] = key end
  if #keys <= ns.Data.WANTED_MAX then return end
  table.sort(keys, function(a, b)
    local ea, eb = t[a], t[b]
    if (ea.points or 0) ~= (eb.points or 0) then return (ea.points or 0) < (eb.points or 0) end
    return ((ea.last and ea.last.t) or 0) < ((eb.last and eb.last.t) or 0)
  end)
  for i = 1, #keys - ns.Data.WANTED_MAX do
    if ns.MapUI then ns.MapUI.RemoveWanted(keys[i]) end
    t[keys[i]] = nil
  end
end

local function entryFor(name, t)
  local tbl = table_()
  if not tbl then return nil end
  local key = Wanted.Key(name)
  if key == "" then return nil end
  local entry = tbl[key]
  if not entry then
    entry = { name = name, points = 0, kills = 0, first = t, victims = {}, kill_times = {} }
    tbl[key] = entry
    cap(tbl)
    if tbl[key] ~= entry then return nil end -- évincé aussitôt : le tableau est plein d'ennemis plus recherchés
  end
  entry.victims = entry.victims or {}
  entry.kill_times = entry.kill_times or {}
  return entry
end

local function refresh(entry)
  if ns.MapUI then ns.MapUI.UpdateWanted(entry) end
  if ns.WantedUI then ns.WantedUI.Refresh() end
end

-- --- morts -----------------------------------------------------------------------------------------------

--- Une mort reçue (ligne « D » décodée). Renvoie l'entrée de l'ennemi et vrai si un point a été ajouté ; nil si le
--- tueur n'est pas un joueur nommé. Doublon (même victime, même heure) : l'entrée, et faux.
function Wanted.RecordDeath(info)
  if type(info) ~= "table" or not info.player then return nil end
  local killer = tostring(info.killer or "")
  if killer == "" or killer == L.KILLER_UNKNOWN then return nil end
  local at = tonumber(info.t) or ns.now()
  local entry = entryFor(killer, at)
  if not entry then return nil end
  for _, victim in ipairs(entry.victims) do
    if victim.guid == info.guid and victim.t == at then return entry, false end
  end
  entry.points = (entry.points or 0) + 1
  if info.kclass and info.kclass ~= "" then entry.class = info.kclass end
  table.insert(entry.victims, { guid = info.guid, name = info.name, class = info.class, t = at })
  while #entry.victims > ns.Data.WANTED_VICTIMS do table.remove(entry.victims, 1) end
  entry.last = {
    kind = "death", t = at, map = info.map, x = info.x, y = info.y, zone = info.zone or "", sub = info.sub or "",
    victim = info.name, victimClass = info.class,
  }
  refresh(entry)
  return entry, true
end

--- Ligne de chat quand un recherché frappe (le popup, s'il est affiché, porte déjà la prime).
function Wanted.Announce(entry, info)
  local place = info.zone ~= "" and info.zone or (info.sub ~= "" and info.sub or L.WHERE_UNKNOWN)
  ns.Print(L.WANTED_CHAT, ns.ClassColored(entry.name, entry.class), ns.ClassColored(info.name, info.class), place, entry.points or 0)
end

-- --- kills -----------------------------------------------------------------------------------------------

local lastHonor = nil -- /mf api : dernier message de victoire honorable { t, text, name, how }
local lastKillAt = 0 -- heure du dernier kill compté, toutes pistes : message, compteur, cadavre
local recentKills = {} -- { name, t } des derniers kills comptés : un même adversaire ne compte pas deux fois d'un coup
local killsBaseline = nil -- victoires honorables du personnage à la dernière lecture (GetPVPLifetimeStats)
local pendingCorpse = nil -- cadavre ciblé en attente de la fenêtre (un seul à la fois)

--- Même personnage : noms égaux, ou le prénom seul d'un côté égal au prénom de l'autre.
local function sameName(a, b)
  a, b = Wanted.Key(a), Wanted.Key(b)
  if a == "" or b == "" then return false end
  if a == b then return true end
  if a:find("%s") and b:find("%s") then return false end
  return a:match("^(%S+)") == b:match("^(%S+)")
end

--- Heure du dernier kill compté pour ce nom dans les `within` dernières secondes, nil sinon.
local function countedRecently(name, t, within)
  for _, kill in ipairs(recentKills) do
    if t - kill.t <= within and sameName(kill.name, name) then return kill.t end
  end
  return nil
end

--- Chaînes du client qui nomment un joueur abattu (le nom en tête, puis le texte propre à chaque variante), et
--- celles connues des clients Forever (classique) et retail (12.0) en secours, si le client n'en expose aucune.
local HONOR_GLOBALS = {
  "COMBATLOG_HONORGAIN", "COMBATLOG_HONORGAIN_NO_RANK", "COMBATLOG_HONORGAIN_EXHAUSTION1",
  "COMBATLOG_HONORGAIN_NO_RANK_EXHAUSTION1",
}
local HONOR_FALLBACKS = {
  "%s meurt, victoire honorable Rang : %s (Points d'honneur estimés : %d)",
  "%s meurt, victoire honorable (Points d'honneur estimés : %d)",
  "%s meurt, victoire honorable. Grade : %s (Points d'honneur estimés : %d)",
  "%s meurt (victoire honorable : %s). Vous gagnez %d points d’honneur.",
  "%s meurt (victoire honorable). Vous gagnez %d points d’honneur.",
  "%s dies, honorable kill Rank: %s (Estimated Honor Points: %d)",
  "%s dies, honorable kill (Estimated Honor Points: %d)",
}

local function escape(s)
  return (s:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0"))
end

--- Motif Lua d'une chaîne de victoire honorable : le texte avant le nom, le nom capturé, puis le texte jusqu'au
--- marqueur suivant (« %s », « %d », « %.2f », « %2$s »…). nil si la chaîne ne nomme personne ou ne dit rien
--- après le nom (un tel motif prendrait n'importe quel message, celui des points d'honneur reçus compris).
function Wanted.HonorPattern(template)
  if type(template) ~= "string" then return nil end
  local s, e = template:find("%%%d*%$?s")
  if not s then return nil end
  local rest = template:sub(e + 1)
  local head = rest:match("^(.-)%%[%d%.%$]*[sdfgcq%%]") or rest
  if head == "" then return nil end
  return "^" .. escape(template:sub(1, s - 1)) .. "(.-)" .. escape(head)
end

local patterns
function Wanted.HonorPatterns()
  if patterns then return patterns end
  patterns = {}
  local seen = {}
  local function add(template)
    local pattern = Wanted.HonorPattern(template)
    if pattern and not seen[pattern] then
      seen[pattern] = true
      patterns[#patterns + 1] = pattern
    end
  end
  for _, name in ipairs(HONOR_GLOBALS) do add(ns.plain(_G[name])) end
  for _, template in ipairs(HONOR_FALLBACKS) do add(template) end
  return patterns
end

--- Texte d'un message de chat sans ses codes d'affichage : couleurs, liens (de joueur : on garde le nom), textures.
function Wanted.CleanMessage(msg)
  msg = tostring(msg):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|T.-|t", ""):gsub("|H.-|h%[?(.-)%]?|h", "%1")
  return (msg:gsub("^%s+", ""):gsub("%s+$", ""))
end

--- Le seul ennemi du tableau dont le nom complet ou le prénom figure dans le texte, en mot entier ; nil si aucun ou
--- plusieurs.
function Wanted.NamedIn(text)
  local lower = " " .. tostring(text or ""):lower() .. " "
  local found = nil
  for key, entry in pairs(table_() or {}) do
    local hit = false
    for _, needle in ipairs({ key, key:match("^(%S+)") or "" }) do
      local s, e = lower:find(needle, 1, true)
      while s and needle ~= "" and not hit do
        local before, after = lower:sub(s - 1, s - 1), lower:sub(e + 1, e + 1)
        if not before:match("[%w\128-\255]") and not after:match("[%w\128-\255]") then hit = true end
        s, e = lower:find(needle, e + 1, true)
      end
      if hit then break end
    end
    if hit then
      if found and found ~= entry then return nil end -- deux ennemis nommés : on ne tranche pas
      found = entry
    end
  end
  return found and found.name or nil
end

--- Nom du joueur abattu d'après un message de victoire honorable (déjà nettoyé) et d'où il vient : « motif »
--- (chaîne du client), « recherché » (message d'une forme inconnue qui nomme un seul ennemi du tableau). nil sinon.
function Wanted.KilledName(msg)
  if type(msg) ~= "string" then return nil end
  for _, pattern in ipairs(Wanted.HonorPatterns()) do
    local name = msg:match(pattern)
    if name and name ~= "" then return name, "motif" end
  end
  local named = Wanted.NamedIn(msg)
  if named then return named, "recherché" end
  return nil
end

--- Message CHAT_MSG_COMBAT_HONOR_GAIN reçu : le kill s'il nomme un joueur abattu ; sinon on note ce qu'on a lu.
function Wanted.OnHonorMessage(char, msg)
  local plain = ns.plain(msg)
  local text = type(plain) == "string" and Wanted.CleanMessage(plain) or nil
  local name, how = Wanted.KilledName(text)
  lastHonor = { t = ns.now(), text = text or (msg ~= nil and "(secret)" or "(vide)"), name = name, how = how }
  ns.Trace("victoire honorable : « %s » → %s", lastHonor.text, name and (name .. " (" .. how .. ")") or "aucun nom")
  if name and char then Wanted.RecordKill(char, name, nil, ns.InBattleground()) end
end

--- Victoires honorables du personnage d'après le client (à vie, sinon de la session) ; nil si illisible.
local function lifetimeKills()
  local fn = GetPVPLifetimeStats or GetPVPSessionStats
  if type(fn) ~= "function" then return nil end
  local ok, hk = pcall(fn)
  return ok and tonumber(ns.plain(hk)) or nil
end

--- Joueur adverse mort que je regarde (cible, survol, focus) : son nom s'il est lisible, "" sinon.
local function deadPlayerAround()
  for _, unit in ipairs({ "target", "mouseover", "focus" }) do
    local ok, exists = pcall(UnitExists or function() end, unit)
    if ok and ns.plain(exists) then
      local okPlayer, player = pcall(UnitIsPlayer or function() end, unit)
      local okDead, dead = pcall(UnitIsDeadOrGhost or function() end, unit)
      local okFriend, friend = pcall(UnitIsFriend or function() end, "player", unit)
      if okPlayer and ns.plain(player) == true and okDead and ns.plain(dead) == true and not (okFriend and ns.plain(friend) == true) then
        local okName, name = pcall(UnitName or function() end, unit)
        name = okName and ns.plain(name) or nil
        if type(name) == "string" and name ~= "" then return name end
      end
    end
  end
  return ""
end

--- Le compteur de victoires honorables du personnage a bougé (PLAYER_PVP_KILLS_CHANGED) : filet quand le message
--- de chat manque ou n'est pas reconnu. On lui laisse WANTED_KILL_WINDOW s ; sans kill lu entre-temps, celui-ci
--- compte, nommé d'après le joueur mort regardé (lu tout de suite : la cible peut disparaître), sans nom sinon
--- (compteur `pk` et événement, mais pas de Wanted faute de nom).
function Wanted.OnKillsChanged(char)
  local hk = lifetimeKills()
  if hk == nil then return end
  local before = killsBaseline
  killsBaseline = hk
  if before == nil or hk <= before then return end
  local at = ns.now()
  if at - lastKillAt < ns.Data.WANTED_KILL_WINDOW then
    ns.Trace("victoires honorables %d → %d : kill déjà lu dans le message", before, hk)
    return
  end
  local victim = deadPlayerAround()
  C_Timer.After(ns.Data.WANTED_KILL_WINDOW, function()
    if lastKillAt >= at then return end -- le message est arrivé entre-temps
    local unread = lastHonor and at - lastHonor.t < ns.Data.WANTED_KILL_WINDOW and lastHonor.text or "(aucun message)"
    lastHonor = { t = ns.now(), text = string.format("%s, victoires honorables %d → %d", unread, before, hk),
      name = victim ~= "" and victim or nil, how = "compteur" }
    ns.Trace("victoires honorables %d → %d sans message reconnu : kill de « %s »", before, hk, victim)
    if char then ns.Safe("wanted.kills", Wanted.RecordKill, char, victim, nil, ns.InBattleground()) end
  end)
end

--- Mon adversaire ciblé est un cadavre : second filet, quand ni message ni compteur n'ont parlé (cible sans honneur,
--- client muet). Lu quand les valeurs de la cible sont lisibles (santé de la cible, changement de cible, fin de
--- combat) ; il faut l'avoir ciblé vivant dans les SEEN_PLAYERS_TTL dernières secondes (souvenir du collecteur des
--- morts, qui ignore les cadavres) et après le dernier kill compté à son nom : un même cadavre compte une fois.
function Wanted.OnTargetMaybeDead(char)
  local ok, exists = pcall(UnitExists or function() end, "target")
  if not (ok and ns.plain(exists)) then return end
  local okPlayer, player = pcall(UnitIsPlayer or function() end, "target")
  local okDead, dead = pcall(UnitIsDeadOrGhost or function() end, "target")
  local okFriend, friend = pcall(UnitIsFriend or function() end, "player", "target")
  if not (okPlayer and ns.plain(player) == true and okDead and ns.plain(dead) == true) then return end
  if okFriend and ns.plain(friend) == true then return end
  local okName, name = pcall(UnitName or function() end, "target")
  name = okName and ns.plain(name) or nil
  if type(name) ~= "string" or name == "" then return end
  local remembered = ns.LastHostile and ns.LastHostile()
  if not (remembered and remembered.player and sameName(remembered.name, name)) then return end
  local at = ns.now()
  if at - (remembered.at or 0) > ns.Data.SEEN_PLAYERS_TTL then return end
  local counted = countedRecently(name, at, ns.Data.SEEN_PLAYERS_TTL)
  if counted and counted >= (remembered.at or 0) then return end -- ce cadavre est déjà compté
  if pendingCorpse and sameName(pendingCorpse, name) then return end
  pendingCorpse = name
  C_Timer.After(ns.Data.WANTED_KILL_WINDOW, function()
    pendingCorpse = nil
    if lastKillAt >= at then return end -- message ou compteur ont parlé entre-temps
    lastHonor = { t = ns.now(), text = string.format("(cadavre de %s ciblé, ni message ni compteur)", name), name = name, how = "cadavre" }
    ns.Trace("cadavre de « %s » ciblé sans message ni compteur : kill", name)
    if char then ns.Safe("wanted.corpse", Wanted.RecordKill, char, name, nil, ns.InBattleground()) end
  end)
end

--- /mf prime <nom> : joue le popup « Prime encaissée » pour un nom du tableau, sans rien enregistrer ni envoyer.
--- Dit si le nom est inconnu du tableau (alors aucun kill ne pourra le faire apparaître).
function Wanted.Rehearse(name)
  name = (tostring(name or ""):gsub("^%s+", ""):gsub("%s+$", ""))
  if name == "" then
    ns.Print(L.PRIME_TEST_USAGE)
    return
  end
  local entry = Wanted.Match(name)
  if not entry then
    local names, n = {}, 0
    for _, e in ipairs(Wanted.Sorted()) do
      n = n + 1
      if n <= 5 then names[#names + 1] = e.name end
    end
    ns.Print(L.PRIME_TEST_NONE, name, n, n > 0 and table.concat(names, ", ") or "aucun")
    return
  end
  local zone = (GetZoneText and ns.plain(GetZoneText())) or ""
  if type(zone) ~= "string" then zone = "" end
  local c = ns.char or {}
  local prime = entry.points or 0
  if ns.UI and ns.UI.ShowBounty then
    ns.UI.ShowBounty(entry, Wanted.BountyPhrase(entry, myName(), prime, zone), myName(), c.class, prime, zone)
  end
  ns.Print(L.PRIME_TEST_OK, ns.ClassColored(entry.name, entry.class), prime)
end

--- /mf api : le dernier message de victoire honorable lu et ce qu'on en a tiré, et le compteur du client.
function Wanted.HonorSource()
  local counter = killsBaseline and tostring(killsBaseline) or "illisibles"
  if not lastHonor then return "aucun message cette session · victoires honorables lues : " .. counter end
  return string.format("dernier message « %s » → %s · victoires honorables lues : %s", lastHonor.text,
    lastHonor.name and string.format("%s (%s)", lastHonor.name, lastHonor.how) or "aucun joueur reconnu", counter)
end

--- Kill déjà compté dans le tableau de l'ennemi (un autre chasseur du groupe, ou l'écho de mon propre « K ») ?
local function killSeen(entry, t)
  for _, seen in ipairs(entry.kill_times or {}) do
    if math.abs(seen - t) < ns.Data.WANTED_KILL_DEDUPE then return true end
  end
  return false
end

local function markKill(entry, t, by, byClass, map, x, y, zone, sub)
  entry.kills = (entry.kills or 0) + 1
  table.insert(entry.kill_times, t)
  while #entry.kill_times > ns.Data.WANTED_VICTIMS do table.remove(entry.kill_times, 1) end
  entry.last = { kind = "kill", t = t, map = map, x = x, y = y, zone = zone or "", sub = sub or "", by = by, byClass = byClass }
  refresh(entry)
end

local function field(s)
  return (tostring(s or ""):gsub("[\t\n]", " "))
end

--- Ligne « K » : j'ai abattu un recherché.
function Wanted.EncodeKill(entry, t, map, x, y, zone, sub)
  local c = ns.char or {}
  local fields = {
    "K", "1", field(c.guid), field(myName()), field(c.class), field(entry.name), tostring(entry.points or 0),
    tostring(entry.kills or 0), tostring(t), map and tostring(map) or "", x and string.format("%.4f", x) or "",
    y and string.format("%.4f", y) or "", field(zone), field(sub), field(entry.class),
  }
  local line = table.concat(fields, "\t")
  for _, i in ipairs({ 14, 13 }) do
    if #line <= 255 then break end
    fields[i] = ""
    line = table.concat(fields, "\t")
  end
  return ns.Positions.Cut(line, 255)
end

local function split(text)
  local fields = {}
  for f in (text .. "\t"):gmatch("([^\t]*)\t") do fields[#fields + 1] = f end
  return fields
end

function Wanted.DecodeKill(text)
  local f = split(text)
  if f[1] ~= "K" or f[2] ~= "1" or #f < 9 or f[6] == "" then return nil end
  return {
    guid = f[3], by = f[4], byClass = f[5], name = f[6], points = tonumber(f[7]) or 0, kills = tonumber(f[8]) or 0,
    t = tonumber(f[9]) or ns.now(), map = tonumber(f[10]), x = tonumber(f[11]), y = tonumber(f[12]),
    zone = f[13] or "", sub = f[14] or "", class = f[15] or "",
  }
end

local function send(text)
  if not (ns.Positions and ns.Positions.Send) then return false end
  return ns.Positions.Send(text)
end

local lastAnnounce = nil -- /mf api : dernier « K » ou « H » envoyé { kind, t, tries, sent, result, repeated }

--- Envoi d'un « K » ou d'un « H » (0.6.7). Le kill tombe en plein combat : le jeu peut refuser l'envoi, et un
--- guildien en combat peut recevoir un texte illisible. Le message part donc tout de suite, puis une seconde fois
--- dès que je suis hors combat ; un envoi refusé est retenté toutes les WANTED_RESEND_DELAY s. Tout s'arrête
--- WANTED_RESEND_MAX s après le kill, avant la fin de la fenêtre de dédoublonnage des receveurs (un message répété
--- ne refait ni popup ni kill chez eux).
local function announceToGuild(text)
  local state = { kind = text:sub(1, 1), t = ns.now(), tries = 1, repeated = false }
  lastAnnounce = state
  state.sent, state.result = send(text)
  if state.sent and not ns.InCombat() then return end
  local deadline = state.t + ns.Data.WANTED_RESEND_MAX
  local function again()
    if ns.now() > deadline then return end
    if not ns.InCombat() or not state.sent then
      state.tries = state.tries + 1
      local sent, result = send(text)
      state.result = result
      if sent then
        state.repeated = state.sent -- déjà parti une fois : c'est la répétition hors combat
        state.sent = true
        if not ns.InCombat() then return end
      end
    end
    C_Timer.After(ns.Data.WANTED_RESEND_DELAY, function() ns.Safe("wanted.resend", again) end)
  end
  C_Timer.After(ns.Data.WANTED_RESEND_DELAY, function() ns.Safe("wanted.resend", again) end)
end

local received = 0 -- « K » et « H » lisibles reçus cette session, les miens (écho) compris

--- /mf api : ce qu'a donné le dernier « K » ou « H » envoyé à la guilde (réponse du jeu, nombre d'essais), et
--- combien j'en ai reçu de lisibles (l'écho des miens compris : zéro après un envoi accepté, rien ne revient).
function Wanted.AnnounceSource()
  local a = lastAnnounce
  local sentText = "aucun K ni H envoyé cette session"
  if a then
    sentText = string.format("dernier %s envoyé : %s · %d essai%s%s", a.kind,
      a.sent and "accepté" or ("refusé (" .. tostring(a.result) .. ")"), a.tries, a.tries > 1 and "s" or "",
      a.repeated and " · répété hors combat" or "")
  end
  return string.format("%s · K et H reçus : %d", sentText, received)
end

local announced = {} -- { name, t } des kills déjà affichés (prime ou victoire honorable), à mon horloge

--- Ce joueur abattu a-t-il déjà son popup depuis moins de WANTED_KILL_DEDUPE s (le groupe annonce autant de fois
--- qu'il a de chasseurs) ?
local function announcedRecently(name, t)
  for _, kill in ipairs(announced) do
    if math.abs(t - kill.t) < ns.Data.WANTED_KILL_DEDUPE and sameName(kill.name, name) then return true end
  end
  return false
end

local function markAnnounced(name, t)
  table.insert(announced, { name = name, t = t })
  while #announced > ns.Data.WANTED_VICTIMS do table.remove(announced, 1) end
end

--- Phrase d'une victoire honorable : le lot des avis de décès, la victime dans le rôle du mort et le chasseur dans
--- celui du tueur. Le message du jeu ne dit ni le niveau ni la classe de la victime : les phrases qui les citent
--- sont laissées de côté.
function Wanted.KillPhrase(victim, by, place)
  local phrases = {}
  for _, phrase in ipairs(ns.PHRASES or {}) do
    if not phrase:find("{niveau}", 1, true) and not phrase:find("{classe}", 1, true) then phrases[#phrases + 1] = phrase end
  end
  if #phrases == 0 then return string.format("%s a abattu %s", by, victim) end
  local values = { personnage = victim, tueur = by, zone = place ~= "" and place or "nulle part" }
  local text = phrases[math.random(1, #phrases)]:gsub("{(%w+)}", function(key) return values[key] or ("{" .. key .. "}") end)
  return (text:gsub("^%l", string.upper))
end

--- Une victoire honorable sur un joueur qui n'est pas recherché (la mienne, ou un « H » reçu) : popup « Victoire
--- honorable », une fois par victime dans la fenêtre, avec « Afficher les morts des autres ». Faux si un popup
--- (celui-ci ou une prime) est déjà passé pour cette victime.
local function announceHonor(victim, victimClass, by, byClass, zone, sub)
  local t = ns.now()
  if announcedRecently(victim, t) then return false end
  markAnnounced(victim, t)
  if not ns.db.settings.showDeaths then return true end
  local place = zone ~= "" and zone or (sub ~= "" and sub or L.WHERE_UNKNOWN)
  if ns.UI and ns.UI.ShowKill then
    ns.UI.ShowKill(victim, victimClass, by, byClass, Wanted.KillPhrase(victim, by, place), place)
  end
  return true
end

--- Ligne « H » : j'ai abattu un joueur qui n'est pas recherché (0.6.6 ; les versions d'avant l'ignorent).
function Wanted.EncodeHonor(name, class, t, zone, sub)
  local c = ns.char or {}
  local fields = {
    "H", "1", field(c.guid), field(myName()), field(c.class), field(name), tostring(t), field(zone), field(sub),
    field(class),
  }
  return ns.Positions.Cut(table.concat(fields, "\t"), 255)
end

function Wanted.DecodeHonor(text)
  local f = split(text)
  if f[1] ~= "H" or f[2] ~= "1" or #f < 7 or f[6] == "" then return nil end
  return {
    guid = f[3], by = f[4], byClass = f[5], name = f[6], t = tonumber(f[7]) or ns.now(), zone = f[8] or "",
    sub = f[9] or "", class = f[10] or "",
  }
end

--- Un recherché abattu (par moi, ou un « K » reçu) : le popup « Prime encaissée » toujours, comme l'avis « WANTED »
--- d'une mort PvP (décision du 9 novembre 2026) ; la ligne de chat seulement avec les alertes Wanted.
local function announceKill(entry, by, byClass, zone, sub, prime)
  local place = zone ~= "" and zone or (sub ~= "" and sub or L.WHERE_UNKNOWN)
  markAnnounced(entry.name, ns.now())
  if ns.db.settings.wantedAlerts then
    ns.Print(L.BOUNTY_CHAT, ns.ClassColored(by, byClass), ns.ClassColored(entry.name, entry.class), place, prime, entry.kills or 0)
  end
  if ns.UI and ns.UI.ShowBounty then
    ns.UI.ShowBounty(entry, Wanted.BountyPhrase(entry, by, prime, place), by, byClass, prime, place)
  end
end

--- Phrase troll d'une prime encaissée. Variables : {chasseur}, {ennemi}, {prime}, {zone}.
function Wanted.BountyPhrase(entry, by, prime, place)
  local phrases = ns.BOUNTY_PHRASES or {}
  if #phrases == 0 then return string.format("%s a abattu %s", by, entry.name) end
  local phrase = phrases[math.random(1, #phrases)]
  local values = {
    chasseur = by, ennemi = entry.name, zone = place ~= "" and place or "nulle part",
    prime = string.format(prime > 1 and L.POINTS_PLURAL or L.POINTS_SINGULAR, prime),
  }
  local text = phrase:gsub("{(%w+)}", function(key) return values[key] or ("{" .. key .. "}") end)
  return (text:gsub("^%l", string.upper))
end

--- Un joueur abattu par moi ou mon groupe (message de victoire honorable). Toujours un événement `pk` du journal
--- avec la prime encaissée ; s'il est recherché, kill au tableau (dédoublonné), message « K », toast. En champ de
--- bataille ou en arène (`battleground`) : le compteur et l'événement (marqué `bg`), rien d'autre.
function Wanted.RecordKill(char, name, t, battleground)
  t = t or ns.now()
  if name ~= "" and countedRecently(name, t, ns.Data.WANTED_KILL_WINDOW) then return nil end -- déjà compté par une autre piste
  local entry = (not battleground) and Wanted.Match(name) or nil
  local prime = entry and entry.points or 0
  local map, x, y = here()
  x, y = round4(x), round4(y)
  local zone = (GetZoneText and ns.plain(GetZoneText())) or ""
  local sub = (GetSubZoneText and ns.plain(GetSubZoneText())) or ""
  if type(zone) ~= "string" then zone = "" end
  if type(sub) ~= "string" then sub = "" end
  ns.Journal.Increment(char, "pk")
  if prime > 0 then ns.Journal.Increment(char, "bounty", prime) end
  local event = { name = name, prime = prime, zone = zone }
  if battleground then event.bg = true end
  if map then event.map = map end
  if x and y then event.x, event.y = x, y end
  ns.Journal.Event(char, "pk", event, t)
  lastKillAt = t
  table.insert(recentKills, { name = name, t = t })
  while #recentKills > ns.Data.WANTED_VICTIMS do table.remove(recentKills, 1) end
  if not entry then
    -- Pas recherché : victoire honorable annoncée à la guilde, sauf en champ de bataille et sans nom lisible.
    if not battleground and name ~= "" then
      local class = ns.SeenPlayerClass and ns.SeenPlayerClass(name) or ""
      if announceHonor(name, class, myName(), char.class, zone, sub) then
        announceToGuild(Wanted.EncodeHonor(name, class, t, zone, sub))
      end
    end
    return nil
  end
  if killSeen(entry, t) then return entry, false end
  markKill(entry, t, myName(), char.class, map, x, y, zone, sub)
  announceToGuild(Wanted.EncodeKill(entry, t, map, x, y, zone, sub))
  announceKill(entry, myName(), char.class, zone, sub, prime)
  return entry, true
end

--- Ligne « K » reçue d'un guildien : kill au tableau (dédoublonné : crédit de groupe, écho), ennemi créé au besoin
--- avec la prime annoncée (le tableau du chasseur peut être plus complet que le mien).
function Wanted.RecordKillMessage(msg, sender)
  local entry = entryFor(msg.name, msg.t)
  if not entry then return nil end
  if msg.class ~= "" and not entry.class then entry.class = msg.class end
  if (msg.points or 0) > (entry.points or 0) then entry.points = msg.points end
  if killSeen(entry, msg.t) then
    if (msg.kills or 0) > (entry.kills or 0) then entry.kills = msg.kills end
    return entry, false
  end
  markKill(entry, msg.t, msg.by, msg.byClass, msg.map, msg.x, msg.y, msg.zone, msg.sub)
  if (msg.kills or 0) > (entry.kills or 0) then entry.kills = msg.kills end
  announceKill(entry, msg.by, msg.byClass, msg.zone, msg.sub, msg.points or 0)
  return entry, true
end

-- --- poignée de main ----------------------------------------------------------------------------------------

--- Résumé du tableau en lignes « W » de 255 octets au plus : W, 1, puis par ennemi
--- nom|classe|prime|kills|dernier t|carte|x|y, les primes les plus fortes d'abord, WANTED_DIGEST_MAX ennemis.
function Wanted.EncodeDigest()
  local lines, fields, line = {}, { "W", "1" }, nil
  local count = 0
  for _, entry in ipairs(Wanted.Sorted()) do
    if count >= ns.Data.WANTED_DIGEST_MAX then break end
    local last = entry.last or {}
    local item = table.concat({
      field(entry.name):gsub("|", "/"), field(entry.class or ""), tostring(entry.points or 0), tostring(entry.kills or 0),
      tostring(last.t or 0), last.map and tostring(last.map) or "", last.x and string.format("%.4f", last.x) or "",
      last.y and string.format("%.4f", last.y) or "",
    }, "|")
    local candidate = table.concat(fields, "\t") .. "\t" .. item
    if #candidate > 255 then
      if #fields > 2 then lines[#lines + 1] = table.concat(fields, "\t") end
      fields = { "W", "1", item }
    else
      fields[#fields + 1] = item
    end
    count = count + 1
  end
  if #fields > 2 then lines[#lines + 1] = table.concat(fields, "\t") end
  return lines
end

function Wanted.DecodeDigest(text)
  local f = split(text)
  if f[1] ~= "W" or f[2] ~= "1" then return nil end
  if #f == 2 then return { request = true } end
  local items = {}
  for i = 3, #f do
    local p = {}
    for part in (f[i] .. "|"):gmatch("([^|]*)|") do p[#p + 1] = part end
    if p[1] and p[1] ~= "" then
      items[#items + 1] = {
        name = p[1], class = p[2] or "", points = tonumber(p[3]) or 0, kills = tonumber(p[4]) or 0,
        t = tonumber(p[5]) or 0, map = tonumber(p[6]), x = tonumber(p[7]), y = tonumber(p[8]),
      }
    end
  end
  return { items = items }
end

--- Résumé reçu : le maximum de chaque valeur, la dernière position la plus récente (sans ses détails).
function Wanted.MergeDigest(items)
  local changed = 0
  for _, item in ipairs(items) do
    local entry = entryFor(item.name, item.t > 0 and item.t or ns.now())
    if entry then
      local before = (entry.points or 0) + (entry.kills or 0)
      if item.class ~= "" and not entry.class then entry.class = item.class end
      if item.points > (entry.points or 0) then entry.points = item.points end
      if item.kills > (entry.kills or 0) then entry.kills = item.kills end
      if item.t > ((entry.last and entry.last.t) or 0) then
        entry.last = { kind = "seen", t = item.t, map = item.map, x = item.x, y = item.y, zone = "", sub = "" }
      end
      if (entry.points or 0) + (entry.kills or 0) ~= before then changed = changed + 1 end
      refresh(entry)
    end
  end
  return changed
end

--- Demande le tableau aux guildiens connectés (à la connexion).
function Wanted.Request()
  requestAt = ns.now()
  send("W\t1")
end

--- Répond à une demande après un délai aléatoire, sauf si un résumé est passé entre-temps (quelqu'un a répondu).
local function answerRequest()
  local at = ns.now()
  requestAt = at
  local lines = Wanted.EncodeDigest()
  if #lines == 0 then return end
  C_Timer.After(1 + math.random() * ns.Data.WANTED_ANSWER_SPREAD, function()
    if digestSeenAt >= at then
      ns.Trace("demande W : quelqu'un a déjà répondu")
      return
    end
    for _, line in ipairs(lines) do send(line) end
    digestSeenAt = ns.now() -- mon propre résumé vaut réponse (l'écho n'en rajoutera pas)
  end)
end

-- --- réception ------------------------------------------------------------------------------------------

local function onAddonMessage(prefix, text, channel, sender)
  if ns.plain(prefix) ~= PREFIX or ns.plain(channel) ~= "GUILD" then return end
  text, sender = ns.plain(text), ns.plain(sender)
  if type(text) ~= "string" then return end
  local kind = text:sub(1, 1)
  if kind == "K" or kind == "H" then received = received + 1 end
  if kind == "K" then
    local msg = Wanted.DecodeKill(text)
    if not msg then return end
    if ns.char and msg.guid == ns.char.guid then
      ns.Trace("reçu K : le mien")
      return
    end
    ns.Trace("reçu K de %s : %s abattu", tostring(sender), msg.name)
    local ok, err = pcall(Wanted.RecordKillMessage, msg, sender)
    if not ok then ns.Store.LogError("wanted.kill", err) end
  elseif kind == "H" then
    local msg = Wanted.DecodeHonor(text)
    if not msg then return end
    if ns.char and msg.guid == ns.char.guid then
      ns.Trace("reçu H : le mien")
      return
    end
    ns.Trace("reçu H de %s : %s abattu", tostring(sender), msg.name)
    -- Recherché chez moi sans l'être chez le chasseur (les tableaux diffèrent) : c'est une prime encaissée.
    local entry = Wanted.Match(msg.name)
    local ok, err
    if entry then
      ok, err = pcall(Wanted.RecordKillMessage, {
        name = entry.name, class = msg.class, points = entry.points or 0, kills = 0, t = msg.t, by = msg.by,
        byClass = msg.byClass, zone = msg.zone, sub = msg.sub,
      }, sender)
    else
      ok, err = pcall(announceHonor, msg.name, msg.class, msg.by, msg.byClass, msg.zone, msg.sub)
    end
    if not ok then ns.Store.LogError("wanted.honor", err) end
  elseif kind == "W" then
    local msg = Wanted.DecodeDigest(text)
    if not msg then return end
    if msg.request then
      ns.Trace("reçu W de %s : demande du tableau", tostring(sender))
      answerRequest()
    else
      digestSeenAt = ns.now()
      local ok, changed = pcall(Wanted.MergeDigest, msg.items)
      if not ok then ns.Store.LogError("wanted.digest", changed) else ns.Trace("reçu W de %s : %d ennemis, %d mis à jour", tostring(sender), #msg.items, changed) end
    end
  end
end

-- --- affichage ---------------------------------------------------------------------------------------------

--- La dernière position est-elle encore à montrer (moins de WANTED_TTL s) ?
function Wanted.Fresh(entry, now)
  local last = entry.last
  return last ~= nil and last.map ~= nil and last.x ~= nil and last.y ~= nil and (last.t or 0) >= (now or ns.now()) - ns.Data.WANTED_TTL
end

--- Zone et sous-zone de la dernière position.
function Wanted.Where(entry)
  local last = entry.last
  if not last then return "" end
  local text = last.zone or ""
  if last.sub and last.sub ~= "" and last.sub ~= last.zone then
    text = text ~= "" and (text .. " · " .. last.sub) or last.sub
  end
  return text
end

--- Ennemis triés : prime décroissante, puis dernière position la plus récente.
function Wanted.Sorted()
  local list = {}
  for _, entry in pairs(table_() or {}) do list[#list + 1] = entry end
  table.sort(list, function(a, b)
    if (a.points or 0) ~= (b.points or 0) then return (a.points or 0) > (b.points or 0) end
    return ((a.last and a.last.t) or 0) > ((b.last and b.last.t) or 0)
  end)
  return list
end

--- Toutes les 10 s : la tête de mort pâlit puis disparaît au bout de WANTED_TTL s.
function Wanted.Tick()
  if not ns.MapUI then return end
  local now = ns.now()
  for key, entry in pairs(table_() or {}) do
    if Wanted.Fresh(entry, now) then ns.MapUI.UpdateWanted(entry) else ns.MapUI.RemoveWanted(key) end
  end
end

--- Case « Alertes Wanted » : décoché, les têtes de mort quittent la carte ; coché, celles encore fraîches reviennent.
function Wanted.SetAlerts(on)
  ns.db.settings.wantedAlerts = on and true or false
  Wanted.Tick()
end

ns.RegisterCollector({
  name = "wanted",
  events = {
    CHAT_MSG_COMBAT_HONOR_GAIN = true, PLAYER_PVP_KILLS_CHANGED = true, CHAT_MSG_ADDON = true,
    UNIT_HEALTH = true, PLAYER_TARGET_CHANGED = true, PLAYER_REGEN_ENABLED = true,
  },
  onLogin = function()
    killsBaseline = lifetimeKills()
    C_Timer.After(5, function() ns.Safe("wanted.tick", Wanted.Tick) end)
    C_Timer.After(ns.Data.WANTED_HANDSHAKE_DELAY, function() ns.Safe("wanted.request", Wanted.Request) end)
    C_Timer.NewTicker(ns.Data.POSITION_TICK, function() ns.Safe("wanted.tick", Wanted.Tick) end)
  end,
  onEvent = function(char, event, ...)
    if event == "CHAT_MSG_COMBAT_HONOR_GAIN" then
      Wanted.OnHonorMessage(char, (...))
    elseif event == "PLAYER_PVP_KILLS_CHANGED" then
      Wanted.OnKillsChanged(char)
    elseif event == "UNIT_HEALTH" then
      if ns.plain((...)) == "target" then Wanted.OnTargetMaybeDead(char) end
    elseif event == "PLAYER_TARGET_CHANGED" or event == "PLAYER_REGEN_ENABLED" then
      Wanted.OnTargetMaybeDead(char)
    else
      onAddonMessage(...)
    end
  end,
  status = function()
    local n, kills = 0, 0
    for _, entry in pairs(table_() or {}) do
      n = n + 1
      kills = kills + (entry.kills or 0)
    end
    return string.format("%d recherchés · %d abattus", n, kills)
  end,
})
