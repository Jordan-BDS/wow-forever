-- Wanted : têtes mises à prix. Un joueur adverse qui tue un membre (mort annoncée par message « D » avec « tueur
-- joueur ») prend un point de prime, jamais remis à zéro (décision du 9 novembre 2026). Le tableau vit au niveau du
-- compte (`db.wanted`, clé = nom en minuscules) : il se remplit avec les morts reçues pendant qu'on est connecté, la
-- sienne comprise ; l'écho de son propre message est reconnu comme un doublon (même victime, même heure). La
-- dernière position connue d'un ennemi est celle de sa victime au moment de mourir, ou celle du chasseur qui l'abat.
--
-- Lot 2 : kills par la guilde. Forever interdit le journal de combat : on lit le message de chat de victoire
-- honorable (« X meurt, victoire honorable… », CHAT_MSG_COMBAT_HONOR_GAIN), que tout le groupe reçoit (crédit de
-- groupe, décidé le 9 novembre 2026). Pas de message pour une cible qui ne rapporte pas d'honneur. Chaque kill de
-- joueur est un événement `pk` du journal (prime encaissée = prime de l'ennemi à ce moment, compteurs `pk` et
-- `bounty`) ; s'il est recherché, message « K » aux guildiens, toast « prime encaissée », tête de mort déplacée.
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

--- Motifs Lua construits depuis les chaînes du jeu « %s meurt, victoire honorable Rang : %s (…) » et sa variante
--- sans rang : on garde le début jusqu'au deuxième marqueur, le nom capturé par le premier.
local patterns
function Wanted.HonorPatterns()
  if patterns then return patterns end
  patterns = {}
  local templates = {
    COMBATLOG_HONORGAIN or "%s meurt, victoire honorable Rang : %s (Points d'honneur estimés : %d)",
    COMBATLOG_HONORGAIN_NO_RANK or "%s meurt, victoire honorable (Points d'honneur estimés : %d)",
  }
  for _, template in ipairs(templates) do
    if type(template) == "string" and template:find("%%s") then
      local rest = template:gsub("^%%s", "", 1) -- le nom est le premier marqueur
      local head = rest:match("^(.-)%%[sd]") or rest -- jusqu'au marqueur suivant
      head = head:gsub("[%^%$%(%)%.%[%]%*%+%-%?]", "%%%0")
      patterns[#patterns + 1] = "^(.-)" .. head
    end
  end
  return patterns
end

--- Nom du joueur abattu d'après un message de victoire honorable, nil sinon.
function Wanted.KilledName(msg)
  if type(msg) ~= "string" then return nil end
  for _, pattern in ipairs(Wanted.HonorPatterns()) do
    local name = msg:match(pattern)
    if name and name ~= "" then return name end
  end
  return nil
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

local function announceKill(entry, by, byClass, zone, sub, prime)
  if not ns.db.settings.wantedAlerts then return end
  local place = zone ~= "" and zone or (sub ~= "" and sub or L.WHERE_UNKNOWN)
  ns.Print(L.BOUNTY_CHAT, ns.ClassColored(by, byClass), ns.ClassColored(entry.name, entry.class), place, prime, entry.kills or 0)
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
  if not entry then return nil end
  if killSeen(entry, t) then return entry, false end
  markKill(entry, t, myName(), char.class, map, x, y, zone, sub)
  send(Wanted.EncodeKill(entry, t, map, x, y, zone, sub))
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
  events = { CHAT_MSG_COMBAT_HONOR_GAIN = true, CHAT_MSG_ADDON = true },
  onLogin = function()
    C_Timer.After(5, function() ns.Safe("wanted.tick", Wanted.Tick) end)
    C_Timer.After(ns.Data.WANTED_HANDSHAKE_DELAY, function() ns.Safe("wanted.request", Wanted.Request) end)
    C_Timer.NewTicker(ns.Data.POSITION_TICK, function() ns.Safe("wanted.tick", Wanted.Tick) end)
  end,
  onEvent = function(char, event, ...)
    if event == "CHAT_MSG_COMBAT_HONOR_GAIN" then
      local name = Wanted.KilledName(ns.plain((...)))
      if name and char then Wanted.RecordKill(char, name, nil, ns.InBattleground()) end
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
