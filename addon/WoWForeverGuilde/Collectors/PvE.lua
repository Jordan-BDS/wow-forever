-- PvE : entrées en instance, boss tués (horodatés, avec la part de guildiens du groupe), instances terminées, morts.
-- Qui m'a tué : rien n'est lisible *au moment* de la mort (le client vide la cible, et en combat les noms sont des
-- valeurs secrètes sur Forever). On lit donc après, ou on se souvient d'avant, dans l'ordre : le récapitulatif de mort
-- du client (coup fatal, lu DEATH_RECAP_DELAY s plus tard, hors combat), la cible au moment de mourir si elle était
-- encore lisible, puis la dernière cible hostile mémorisée (nom lu à son ciblage, gardé KILLER_MEMORY s avant le combat
-- et tout le combat). L'annonce part après ce délai ; le compteur et l'événement du journal sont immédiats.
-- Wanted : si le tueur est un joueur, l'événement le dit (`player`), avec sa classe (`kclass`) et la position du mort
-- (`map`, `x`, `y`) : c'est « là où il a frappé », la seule position connue de lui. Joueur ou créature (`UnitIsPlayer`,
-- illisible en combat) se lit sur la cible ou le souvenir qui porte le nom du tueur, sinon parmi les joueurs hostiles
-- lus dans les SEEN_PLAYERS_TTL dernières secondes (cible, survol, plaques de nom), sinon sur les unités encore
-- autour une fois mort (cible, survol, focus, plaques) : un voleur jamais ciblé est reconnu si sa plaque est là.
-- En champ de bataille ou en arène, la mort compte au journal mais n'est ni annoncée ni rapprochée d'un joueur :
-- pas de Wanted en instance PvP.
local ADDON, ns = ...

local inInstance = false
local lastHostile = nil -- { name, player, class, at } : dernière cible hostile dont le nom était lisible
local combatSince = nil -- début du combat en cours (PLAYER_REGEN_DISABLED)
local deathsThisSession = 0 -- identifiant du récapitulatif : le client les numérote par session
local lastSource = nil -- d'où venait le tueur de la dernière mort, pour /mf api (« Tests en jeu »)
local dead = false -- mort déjà comptée, jusqu'au retour à la vie : un second PLAYER_DEAD pour la même mort est ignoré
local seenPlayers = {} -- clé = nom en minuscules → { name, class, at } : joueurs hostiles lus (cible, survol, plaque)

local function guildmatesInGroup()
  local count, members = 0, {}
  local n = (GetNumGroupMembers and GetNumGroupMembers()) or 0
  local prefix = (IsInRaid and IsInRaid()) and "raid" or "party"
  for i = 1, n do
    local unit = prefix .. i
    if UnitExists and UnitExists(unit) and UnitIsInMyGuild and UnitIsInMyGuild(unit) then
      count = count + 1
      local guid = UnitGUID and UnitGUID(unit)
      if guid then members[#members + 1] = guid end
    end
  end
  if UnitIsInMyGuild == nil or n == 0 then count = 1 end -- le joueur lui-même
  return count, members
end

--- Texte lu sous protection : un appel qui échoue ou une valeur « secrète » (en combat) donne "" plutôt qu'une
--- erreur qui ferait sauter tout le traitement de la mort, annonce comprise.
local function text(fn, ...)
  if type(fn) ~= "function" then return "" end
  local ok, value = pcall(fn, ...)
  value = ok and ns.plain(value) or nil
  return type(value) == "string" and value or ""
end

--- L'unité (« target », « mouseover », « nameplate3 »…) si elle existe et est lisible, hostile sauf si `anyone` :
--- { name, player, class } ; nil sinon. `player` et `class` sont lus sous protection (en combat ils peuvent être
--- secrets) : alors faux et "".
local function readUnit(unit, anyone)
  if type(unit) ~= "string" then return nil end
  local ok, exists = pcall(UnitExists or function() end, unit)
  if not (ok and ns.plain(exists)) then return nil end
  if UnitCanAttack and not anyone then
    local okAttack, hostile = pcall(UnitCanAttack, "player", unit)
    if okAttack and ns.plain(hostile) == false then return nil end
  end
  local name = ns.UnitDisplayName(unit)
  if not name then return nil end
  local okPlayer, player = pcall(UnitIsPlayer or function() end, unit)
  local okClass, _, class = pcall(UnitClass or function() end, unit)
  class = okClass and ns.plain(class) or nil
  local okGuid, guid = pcall(UnitGUID or function() end, unit)
  guid = okGuid and ns.plain(guid) or nil
  return {
    name = name, player = okPlayer and ns.plain(player) == true, class = type(class) == "string" and class or "",
    guid = type(guid) == "string" and guid or nil,
  }
end

local function nameKey(s)
  return (tostring(s or ""):gsub("^%s+", ""):gsub("%s+$", "")):lower()
end

--- Même personnage : noms égaux, ou le prénom seul d'un côté égal au prénom de l'autre (le récapitulatif et les
--- unités ne donnent pas toujours prénom et nom ensemble).
local function sameName(a, b)
  a, b = nameKey(a), nameKey(b)
  if a == "" or b == "" then return false end
  if a == b then return true end
  if a:find("%s") and b:find("%s") then return false end
  return a:match("^(%S+)") == b:match("^(%S+)")
end

--- Un joueur hostile lu : on le retient SEEN_PLAYERS_TTL s comme joueur, avec sa classe.
local function rememberPlayer(seen, t)
  if not (seen and seen.player) then return end
  seenPlayers[nameKey(seen.name)] = { name = seen.name, class = seen.class or "", at = t, guid = seen.guid }
end

--- Un joueur hostile lu dans les SEEN_PLAYERS_TTL dernières secondes, par son nom ou par son identifiant (en
--- combat le nom d'un adversaire peut être secret, pas forcément son identifiant) : son nom, nil s'il est inconnu.
function ns.SeenPlayer(name, guid)
  local t = ns.now()
  for _, seen in pairs(seenPlayers) do
    if t - (seen.at or 0) <= ns.Data.SEEN_PLAYERS_TTL then
      if guid and seen.guid == guid then return seen.name end
      if name and name ~= "" and sameName(seen.name, name) then return seen.name end
    end
  end
  return nil
end

local function forgetOldPlayers(t)
  for key, seen in pairs(seenPlayers) do
    if t - (seen.at or 0) > ns.Data.SEEN_PLAYERS_TTL then seenPlayers[key] = nil end
  end
end

--- Ciblage : on retient la dernière cible hostile lisible (hors combat le nom est en clair ; en combat il est
--- secret et on garde la précédente).
local function rememberTarget()
  local target = readUnit("target")
  if not target then return end
  local okDead, dead = pcall(UnitIsDeadOrGhost or function() end, "target")
  if okDead and ns.plain(dead) == true then return end -- un cadavre n'est ni un tueur ni une cible vivante
  target.at = ns.now()
  lastHostile = target
  rememberPlayer(target, target.at)
end

--- Classe d'un joueur hostile lu dans les SEEN_PLAYERS_TTL dernières secondes, "" s'il est inconnu.
function ns.SeenPlayerClass(name)
  local t = ns.now()
  for _, seen in pairs(seenPlayers) do
    if t - (seen.at or 0) <= ns.Data.SEEN_PLAYERS_TTL and sameName(seen.name, name) then return seen.class or "" end
  end
  return ""
end

--- Pour le Wanted : la dernière cible hostile lisible, ciblée vivante ({ name, player, class, at }).
function ns.LastHostile()
  return lastHostile
end

--- Les unités lisibles autour de moi : cible, survol, focus, cible de la cible, et les plaques de nom affichées.
local function unitsAround()
  local tokens = { "target", "mouseover", "focus", "targettarget" }
  local ok, plates = pcall((C_NamePlate and C_NamePlate.GetNamePlates) or function() end)
  plates = ok and ns.plain(plates) or nil
  if type(plates) == "table" then
    for _, plate in ipairs(plates) do
      local token = type(plate) == "table" and ns.plain(plate.namePlateUnitToken)
      if type(token) == "string" then tokens[#tokens + 1] = token end
    end
  else
    for i = 1, 40 do tokens[#tokens + 1] = "nameplate" .. i end
  end
  return tokens
end

--- Souvenir encore valable : ciblé pendant le combat en cours, ou dans les KILLER_MEMORY s qui l'ont précédé.
local function rememberedKiller(t)
  if not lastHostile then return nil end
  local since = (combatSince or t) - ns.Data.KILLER_MEMORY
  return lastHostile.at >= since and lastHostile or nil
end

--- Récapitulatif de mort du client : nom de la source du coup fatal, ou cause environnementale (chute, lave…).
--- Renvoie aussi si l'API existe, pour la note de diagnostic.
local function recapKiller(recapID)
  local get = (C_DeathInfo and C_DeathInfo.GetDeathRecapEvents) or GetDeathRecapEvents
  if type(get) ~= "function" then return nil, nil, false end
  local ok, events = pcall(get, recapID)
  if not ok or type(events) ~= "table" then return nil, nil, true end
  for i = #events, 1, -1 do -- le dernier événement est le coup fatal
    local e = events[i]
    if type(e) == "table" then
      local env = ns.plain(e.environmentalDamageType)
      if type(env) == "string" and env ~= "" then return nil, env, true end
      local name = ns.plain(e.sourceName)
      if type(name) == "string" and name ~= "" then return name, nil, true end
    end
  end
  return nil, nil, true
end

--- Le tueur nommé était-il un joueur, et de quelle classe ? D'après la cible ou le souvenir qui porte ce nom (le
--- récapitulatif ne donne qu'un nom), sinon les joueurs hostiles lus récemment, sinon les unités encore autour.
--- Renvoie aussi d'où vient la réponse. Inconnu → nil : la mort ne fera pas de Wanted.
local function killerIdentity(name, target, remembered, t)
  if target and sameName(target.name, name) then return target.player == true, target.class or "", "cible" end
  if remembered and sameName(remembered.name, name) then
    return remembered.player == true, remembered.class or "", "mémoire"
  end
  for _, seen in pairs(seenPlayers) do
    if t - (seen.at or 0) <= ns.Data.SEEN_PLAYERS_TTL and sameName(seen.name, name) then
      return true, seen.class or "", "joueur vu"
    end
  end
  for _, token in ipairs(unitsAround()) do
    local seen = readUnit(token, true)
    if seen and sameName(seen.name, name) then return seen.player == true, seen.class or "", "autour" end
  end
  return nil, "", nil
end

--- Complète l'événement de mort (tueur ou cause) puis annonce. `target` : cible lisible au moment de mourir ;
--- `remembered` : souvenir valable à ce moment-là (tous deux figés à PLAYER_DEAD, la mémoire est remise à zéro ensuite).
local function resolveDeath(char, death, target, remembered, recapID, battleground)
  if battleground then
    lastSource = "mort en champ de bataille ou en arène : ni annonce, ni Wanted"
    return
  end
  local name, env, recapApi = recapKiller(recapID)
  local source = (name or env) and "récap" or nil
  if not source and target then name, source = target.name, "cible" end
  if not source and remembered then name, source = remembered.name, "mémoire" end
  death.killer = name
  death.env = env
  local identity = "sans objet"
  if name then
    local player, class, how = killerIdentity(name, target, remembered, ns.now())
    if player then death.player = true end
    if class ~= "" then death.kclass = class end
    identity = how and ((player and "oui" or "non") .. " d'après " .. how) or "inconnu"
  end
  lastSource = string.format("tueur d'après %s (récap %s), joueur %s", source or "rien, inconnu",
    recapApi and "présent" or "absent", identity)
  if ns.OnDeath then ns.Safe("deaths.announce", ns.OnDeath, char, death) end
end

--- Pour /mf api : comment le tueur de la dernière mort a été trouvé, nil sans mort cette session.
function ns.DeathSource()
  return lastSource
end

ns.RegisterCollector({
  name = "pve",
  events = {
    PLAYER_ENTERING_WORLD = true, ENCOUNTER_END = true, PLAYER_DEAD = true, PLAYER_ALIVE = true, PLAYER_UNGHOST = true,
    PLAYER_TARGET_CHANGED = true, PLAYER_REGEN_DISABLED = true,
    NAME_PLATE_UNIT_ADDED = true, UPDATE_MOUSEOVER_UNIT = true,
  },
  onEvent = function(char, event, ...)
    if event == "PLAYER_ENTERING_WORLD" then
      local inside, kind = IsInInstance()
      if inside and (kind == "party" or kind == "raid") and not inInstance then
        local name, _, _, _, _, _, _, instanceId = GetInstanceInfo()
        ns.Journal.Increment(char, kind == "raid" and "raids_entered" or "dungeons_entered")
        ns.Journal.Event(char, "enter", { instance = instanceId, name = name, raid = kind == "raid" })
      end
      inInstance = inside and (kind == "party" or kind == "raid") or false
    elseif event == "PLAYER_TARGET_CHANGED" then
      rememberTarget()
    elseif event == "NAME_PLATE_UNIT_ADDED" then
      rememberPlayer(readUnit(ns.plain(...)), ns.now())
    elseif event == "UPDATE_MOUSEOVER_UNIT" then
      rememberPlayer(readUnit("mouseover"), ns.now())
    elseif event == "PLAYER_REGEN_DISABLED" then
      dead = false -- on n'entre en combat que vivant
      combatSince = ns.now()
      rememberTarget() -- entrée en combat sur une cible déjà choisie
    elseif event == "ENCOUNTER_END" then
      local encounterId, name, _, groupSize, success = ...
      if ns.plain(success) == 1 then
        local guildCount, guildMembers = guildmatesInGroup()
        ns.Journal.Increment(char, "boss_kills")
        local bosses = char.counters.bosses
        if type(bosses) ~= "table" then bosses = {}; char.counters.bosses = bosses end
        local key = tostring(encounterId)
        local record = bosses[key] or { n = 0, first = ns.now(), name = name }
        record.n = record.n + 1
        record.last = ns.now()
        bosses[key] = record
        ns.Journal.Event(char, "boss", { id = encounterId, name = name, size = groupSize, guild = guildCount, members = ns.Json.array(guildMembers) })
        local final = ns.Data.FINAL_BOSSES[encounterId]
        if final then
          ns.Journal.Increment(char, final.raid and "raids_done" or "dungeons_done")
          ns.Journal.Event(char, "clear", { instance = final.instance })
        end
      end
    elseif event == "PLAYER_UNGHOST" then
      dead = false
    elseif event == "PLAYER_ALIVE" then
      -- Aussi envoyé en libérant son esprit : on n'est vivant que si le client le dit.
      local okDead, still = pcall(UnitIsDeadOrGhost or function() end, "player")
      if okDead and ns.plain(still) == false then dead = false end
    elseif event == "PLAYER_DEAD" then
      if dead then
        ns.Trace("PLAYER_DEAD reçu deux fois pour la même mort : ignoré")
        return
      end
      dead = true
      local t = ns.now()
      ns.Journal.Increment(char, "deaths")
      deathsThisSession = deathsThisSession + 1
      local zone, sub = text(GetZoneText), text(GetSubZoneText)
      local okTarget, target = pcall(readUnit, "target")
      local remembered = rememberedKiller(t)
      forgetOldPlayers(t)
      local death = ns.Journal.Event(char, "death", { zone = zone, sub = sub, level = char.level })
      -- Où je meurs (carte et coordonnées), pour la dernière position connue du tueur s'il est un joueur.
      if ns.Positions and ns.Positions.Here then
        local okHere, map, x, y = pcall(ns.Positions.Here)
        if okHere and map then
          death.map = map
          if x and y then death.x, death.y = math.floor(x * 10000 + 0.5) / 10000, math.floor(y * 10000 + 0.5) / 10000 end
        end
      end
      local recapID, battleground = deathsThisSession, ns.InBattleground()
      C_Timer.After(ns.Data.DEATH_RECAP_DELAY, function()
        ns.Safe("deaths.resolve", resolveDeath, char, death, okTarget and target or nil, remembered, recapID, battleground)
      end)
      combatSince = nil
    end
  end,
  status = function(char)
    local c = char.counters or {}
    return string.format("%d boss · %d donjons · %d morts · %d créatures", c.boss_kills or 0, c.dungeons_done or 0, c.deaths or 0, c.kills or 0)
  end,
})
