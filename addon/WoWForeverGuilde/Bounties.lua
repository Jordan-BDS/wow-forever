-- Primes posées à la main : un membre met tant d'or par kill sur un joueur adverse, pour un nombre de kills au
-- plus. Posée en jeu (`/mf prime <or> [kills]` sur la cible, ou `/mf prime <nom> <or> [kills]`) ou sur le site
-- (page Primes) ; le site compte les kills et tient les comptes, l'addon alerte.
--
-- Les primes vivent au niveau du compte (`db.bounties`, clé = identifiant de la prime). Une prime posée en jeu
-- part aux guildiens connectés par un message « B » et remonte au site dans l'export de chacun de ceux qui la
-- connaissent (le premier qui se déconnecte la fait arriver). Celles du site, et l'état de toutes (kills comptés,
-- prime terminée ou annulée), reviennent par le compagnon, jeu fermé. À la connexion on demande les primes aux
-- guildiens (« B » sans rien) ; un membre répond après un délai aléatoire, sauf si quelqu'un l'a déjà fait.
--
-- Cible vue : un joueur adverse lu (plaque de nom, cible, survol : PvE.lua) dont le nom porte une prime en cours.
-- On n'envoie rien pour les autres joueurs. Celui qui la voit attend un court délai aléatoire puis l'annonce
-- par un message « S » (qui, où, quand), sauf si un guildien vient de le faire : une seule annonce par cible et
-- par BOUNTY_SEEN_DEDUPE s. Chez tous : une pièce d'or sur la carte à cet endroit pendant BOUNTY_SEEN_TTL s, et
-- un popup, au plus un par cible et par BOUNTY_ALERT_REPEAT s (case « Alertes de primes »). Rien en champ de
-- bataille ni en arène.
--
-- Prime de guilde (`kind = "g"`, `/mf prime guilde <or> [kills]`) : la cible est une guilde adverse, `name` est
-- son nom. Chaque membre vu ou abattu compte, s'il a été lu avec sa guilde (plaque de nom, cible, survol) : le
-- message de victoire honorable ne nomme que la victime, sa guilde vient de ce qu'on a lu de lui juste avant.
--
-- Kills : l'addon compte ceux qu'il voit (les siens, les « K » et « H » des guildiens) pour savoir quand une prime
-- est finie ; c'est une estimation, le compte qui fait foi est celui du site. Le kill du commanditaire ne compte
-- pas : il ne se doit rien.
local ADDON, ns = ...

local Bounties = {}
ns.Bounties = Bounties
local L = ns.L

local digests = 0 -- primes redites reçues (« B » qui n'est pas une pose) : une de plus, quelqu'un a répondu
local pending = {} -- identifiant de prime → vrai : cible vue, annonce en attente du délai aléatoire
local lastKills = {} -- identifiant de prime, prénom de la victime → heure du dernier kill compté (dédoublonnage)

local function table_()
  local db = ns.db
  if not db then return nil end
  db.bounties = db.bounties or {}
  return db.bounties
end

local function trim(s)
  return (tostring(s or ""):gsub("^%s+", ""):gsub("%s+$", ""))
end

local function key(name)
  return trim(name):lower()
end

--- Même personnage : noms égaux, ou le prénom seul d'un côté égal au prénom de l'autre (comme le Wanted).
local function sameName(a, b)
  a, b = key(a), key(b)
  if a == "" or b == "" then return false end
  if a == b then return true end
  if a:find("%s") and b:find("%s") then return false end
  return a:match("^(%S+)") == b:match("^(%S+)")
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

local function zones()
  local zone = (GetZoneText and ns.plain(GetZoneText())) or ""
  local sub = (GetSubZoneText and ns.plain(GetSubZoneText())) or ""
  return type(zone) == "string" and zone or "", type(sub) == "string" and sub or ""
end

local function round4(v)
  return v and math.floor(v * 10000 + 0.5) / 10000 or nil
end

local function field(s)
  return (tostring(s or ""):gsub("[\t\n]", " "))
end

local function split(text)
  local fields = {}
  for f in (text .. "\t"):gmatch("([^\t]*)\t") do fields[#fields + 1] = f end
  return fields
end

local function send(text)
  if not (ns.Positions and ns.Positions.Send) then return false end
  return ns.Positions.Send(text)
end

--- La prime vise-t-elle ce joueur ? Par son nom, ou par sa guilde pour une prime de guilde.
local function targets(entry, name, guild)
  if entry.kind == "g" then return guild ~= nil and guild ~= "" and key(guild) == key(entry.name) end
  return sameName(entry.name, name)
end

--- « la guilde Les Kor'kron » pour une prime de guilde, le nom du joueur sinon.
function Bounties.Label(entry)
  if entry.kind == "g" then return string.format(L.BOUNTY_GUILD_LABEL, entry.name) end
  return entry.name
end

--- Prime en cours : ni annulée, ni fermée par le site, et il reste des kills à payer.
function Bounties.Open(entry)
  return entry ~= nil and not entry.cancelled and not entry.closed and (entry.kills or 0) < (entry.max or 1)
end

--- La prime en cours la plus forte sur ce joueur (son nom, ou sa guilde si on la connaît), nil s'il n'y en a pas.
function Bounties.Match(name, guild)
  if key(name) == "" then return nil end
  if not guild and ns.SeenPlayerGuild then guild = ns.SeenPlayerGuild(name) end
  local best
  for _, entry in pairs(table_() or {}) do
    if Bounties.Open(entry) and targets(entry, name, guild) and (not best or (entry.gold or 0) > (best.gold or 0)) then
      best = entry
    end
  end
  return best
end

--- Primes en cours, les plus fortes d'abord. `all` : avec les terminées et les annulées.
function Bounties.Sorted(all)
  local list = {}
  for _, entry in pairs(table_() or {}) do
    if all or Bounties.Open(entry) then list[#list + 1] = entry end
  end
  table.sort(list, function(a, b)
    if (a.gold or 0) ~= (b.gold or 0) then return (a.gold or 0) > (b.gold or 0) end
    return (a.t or 0) > (b.t or 0)
  end)
  return list
end

--- Garde au plus BOUNTY_MAX primes : les plus anciennes qui ne sont plus en cours sautent d'abord.
local function cap()
  local tbl = table_()
  local list = Bounties.Sorted(true)
  if #list <= ns.Data.BOUNTY_MAX then return end
  table.sort(list, function(a, b)
    local oa, ob = Bounties.Open(a), Bounties.Open(b)
    if oa ~= ob then return ob end
    return (a.t or 0) < (b.t or 0)
  end)
  for i = 1, #list - ns.Data.BOUNTY_MAX do tbl[list[i].id] = nil end
end

--- La dernière observation est-elle encore à montrer sur la carte ?
function Bounties.Fresh(entry, now)
  local seen = entry.seen
  return seen ~= nil and seen.map ~= nil and seen.x ~= nil and seen.y ~= nil
    and (seen.t or 0) >= (now or ns.now()) - ns.Data.BOUNTY_SEEN_TTL
end

--- Lieu de la dernière observation.
function Bounties.Where(entry)
  local seen = entry.seen
  if not seen then return "" end
  local text = seen.zone or ""
  if seen.sub and seen.sub ~= "" and seen.sub ~= seen.zone then
    text = text ~= "" and (text .. " · " .. seen.sub) or seen.sub
  end
  return text
end

--- « 50 po par kill », « 2 × Lotus noir par kill » pour une prime en objets (posée sur le site), ou les deux ;
--- et « 2/5 kills » quand la prime en paie plusieurs.
function Bounties.Reward(entry)
  local text
  if type(entry.item) == "string" and entry.item ~= "" then
    text = string.format(L.BOUNTY_ITEM, entry.item)
    if (entry.gold or 0) > 0 then text = string.format(L.BOUNTY_GOLD, entry.gold) .. " + " .. text end
  else
    text = string.format(L.BOUNTY_GOLD, entry.gold or 0)
  end
  if (entry.max or 1) > 1 then text = text .. " · " .. string.format(L.BOUNTY_KILLS, entry.kills or 0, entry.max) end
  return text
end

local function refresh(entry)
  if ns.MapUI and ns.MapUI.UpdateBounty then ns.MapUI.UpdateBounty(entry) end
  if ns.Nameplates then ns.Nameplates.Refresh() end
end

-- --- messages ---------------------------------------------------------------------------------------------

--- B, 1, identifiant, commanditaire (guid, nom, classe), cible, or par kill, kills payés, heure de pose, heure
--- d'annulation (0 : en cours), kills comptés, 1 si la prime vient d'être posée (annonce chez les guildiens),
--- « g » pour une prime de guilde.
function Bounties.Encode(entry, live)
  local fields = {
    "B", "1", field(entry.id), field(entry.guid or ""), field(entry.by or ""), field(entry.byClass or ""),
    field(entry.name), tostring(entry.gold or 0), tostring(entry.max or 1), tostring(entry.t or 0),
    tostring(entry.cancelled or 0), tostring(entry.kills or 0), live and "1" or "0",
  }
  if entry.kind == "g" then fields[14] = "g" end
  return table.concat(fields, "\t")
end

function Bounties.Decode(text)
  local f = split(text)
  if f[1] ~= "B" or f[2] ~= "1" then return nil end
  if #f == 2 then return { request = true } end
  local gold, max, t = tonumber(f[8]), tonumber(f[9]), tonumber(f[10])
  if not f[3] or f[3] == "" or trim(f[7]) == "" or not gold or not max or not t then return nil end
  if gold < 1 or gold > ns.Data.BOUNTY_MAX_GOLD or max < 1 or max > ns.Data.BOUNTY_MAX_KILLS then return nil end
  return {
    id = f[3], guid = f[4] ~= "" and f[4] or nil, by = f[5] or "", byClass = f[6] ~= "" and f[6] or nil,
    name = trim(f[7]), gold = math.floor(gold), max = math.floor(max), t = t,
    cancelled = tonumber(f[11]) or 0, kills = tonumber(f[12]) or 0, live = f[13] == "1",
    kind = f[14] == "g" and "g" or nil,
  }
end

--- S, 1, identifiant de la prime, guetteur (guid, nom, classe), cible (nom, classe), heure, carte, x, y, zone,
--- sous-zone.
function Bounties.EncodeSeen(entry, seen)
  local c = ns.char or {}
  return table.concat({
    "S", "1", field(entry.id), field(c.guid or ""), field(seen.by or ""), field(seen.byClass or ""),
    field(seen.name or entry.name), field(seen.class or ""), tostring(seen.t or 0),
    seen.map and tostring(seen.map) or "", seen.x and string.format("%.4f", seen.x) or "",
    seen.y and string.format("%.4f", seen.y) or "", field(seen.zone or ""), field(seen.sub or ""),
  }, "\t")
end

function Bounties.DecodeSeen(text)
  local f = split(text)
  if f[1] ~= "S" or f[2] ~= "1" or not f[3] or f[3] == "" then return nil end
  return {
    id = f[3], guid = f[4] or "", by = f[5] or "", byClass = f[6] ~= "" and f[6] or nil, name = f[7] or "",
    class = f[8] or "", t = tonumber(f[9]) or ns.now(), map = tonumber(f[10]), x = tonumber(f[11]),
    y = tonumber(f[12]), zone = f[13] or "", sub = f[14] or "",
  }
end

-- --- pose et annulation -------------------------------------------------------------------------------------

--- Pose une prime et l'annonce à la guilde. Renvoie la prime, nil si le personnage n'est pas encore connu.
function Bounties.Post(name, gold, max, kind)
  local c, tbl = ns.char, table_()
  if not (c and c.guid and tbl) then return nil end
  local t = ns.now()
  local id = (tostring(c.guid):gsub("[^%w]", "")):sub(-10) .. "-" .. tostring(t)
  local entry = {
    id = id, name = trim(name), gold = gold, max = max or 1, t = t, by = myName(), byClass = c.class, guid = c.guid,
    kills = 0, kind = kind == "g" and "g" or nil,
  }
  tbl[id] = entry
  cap()
  send(Bounties.Encode(entry, true))
  ns.Print(L.BOUNTY_POSTED, Bounties.Label(entry), Bounties.Reward(entry))
  refresh(entry)
  return entry
end

--- Ma prime en cours sur ce nom (de joueur, ou de guilde si `kind` vaut « g »), posée en jeu ou sur le site.
local function mine(name, kind)
  local c = ns.char or {}
  for _, entry in pairs(table_() or {}) do
    local same = (entry.kind == "g") == (kind == "g")
      and (kind == "g" and key(entry.name) == key(name) or kind ~= "g" and sameName(entry.name, name))
    if Bounties.Open(entry) and same and (entry.guid == c.guid or (not entry.guid and entry.by == myName())) then
      return entry
    end
  end
  return nil
end

--- Annule ma prime sur ce nom. Les kills déjà faits restent dus.
function Bounties.Cancel(name, kind)
  local entry = mine(name, kind)
  if not entry then
    ns.Print(L.BOUNTY_CANCEL_NONE, kind == "g" and string.format(L.BOUNTY_GUILD_LABEL, name) or name)
    return false
  end
  if not entry.guid then -- posée sur le site : elle s'y annule
    ns.Print(L.BOUNTY_CANCEL_SITE, Bounties.Label(entry))
    return false
  end
  entry.cancelled = ns.now()
  send(Bounties.Encode(entry, false))
  ns.Print(L.BOUNTY_CANCELLED, Bounties.Label(entry))
  if ns.MapUI and ns.MapUI.RemoveBounty then ns.MapUI.RemoveBounty(entry.id) end
  if ns.Nameplates then ns.Nameplates.Refresh() end
  return true
end

--- Le nom du joueur adverse ciblé, ou celui de sa guilde (`guild`) ; nil (et la raison dite) si la cible ne
--- convient pas.
local function targetName(guild)
  local ok, exists = pcall(UnitExists or function() end, "target")
  if not (ok and ns.plain(exists)) then
    ns.Print(L.BOUNTY_NEED_TARGET)
    return nil
  end
  local okPlayer, player = pcall(UnitIsPlayer or function() end, "target")
  local okAttack, hostile = pcall(UnitCanAttack or function() end, "player", "target")
  if not (okPlayer and ns.plain(player) == true) or not (okAttack and ns.plain(hostile) == true) then
    ns.Print(L.BOUNTY_NEED_ENEMY)
    return nil
  end
  if guild then
    local found = ns.UnitGuild("target")
    if not found then ns.Print(L.BOUNTY_NO_GUILD) end
    return found
  end
  local name = ns.UnitDisplayName("target")
  if not name then ns.Print(L.BOUNTY_NAME_HIDDEN) end
  return name
end

--- « guilde » ou « guilde <reste> » en tête : vrai et le reste ; sinon faux et le texte tel quel.
local function guildWord(text)
  local lower = text:lower()
  if lower == "guilde" or lower:match("^guilde%s") then return true, trim(text:sub(7)) end
  return false, text
end

local function list()
  local open = Bounties.Sorted()
  if #open == 0 then
    ns.Print(L.BOUNTY_LIST_NONE)
  else
    for _, entry in ipairs(open) do
      ns.Print(L.BOUNTY_LIST_LINE, Bounties.Label(entry), Bounties.Reward(entry), entry.by or "?")
    end
  end
  ns.Print(L.BOUNTY_USAGE)
end

--- /mf prime : seul, la liste ; `<or> [kills]` sur la cible ; `<nom> <or> [kills]` ; `annuler [nom]` ;
--- `guilde <or> [kills]` sur la guilde de la cible, `guilde <nom de guilde> <or> [kills]`, `annuler guilde [nom]` ;
--- `test <nom>` (ou un nom seul, l'usage d'avant) joue le popup « Prime encaissée » du Wanted.
function Bounties.Command(rest)
  rest = trim(rest)
  if rest == "" then return list() end
  local lower = rest:lower()
  if lower == "test" or lower:match("^test%s") then return ns.Wanted.Rehearse(rest:sub(5)) end
  if lower == "annuler" or lower:match("^annuler%s") then
    local guild, name = guildWord(trim(rest:sub(8)))
    if name == "" then name = targetName(guild) end
    if name then Bounties.Cancel(name, guild and "g" or nil) end
    return
  end
  local guild, body = guildWord(rest)
  local name, gold, max = body:match("^(.-)%s*(%d+)%s+(%d+)$")
  if not gold then name, gold = body:match("^(.-)%s*(%d+)$") end
  if not gold then
    if guild then return ns.Print(L.BOUNTY_USAGE) end
    return ns.Wanted.Rehearse(rest)
  end
  gold, max, name = tonumber(gold), tonumber(max) or 1, trim(name)
  if gold < 1 or gold > ns.Data.BOUNTY_MAX_GOLD or max < 1 or max > ns.Data.BOUNTY_MAX_KILLS then
    ns.Print(L.BOUNTY_BAD_AMOUNT, ns.Data.BOUNTY_MAX_GOLD, ns.Data.BOUNTY_MAX_KILLS)
    return
  end
  local kind = guild and "g" or nil
  if name == "" then name = targetName(guild) end
  if not name then return end
  if #name < 2 or #name > 64 then
    ns.Print(L.BOUNTY_USAGE)
    return
  end
  local label = guild and string.format(L.BOUNTY_GUILD_LABEL, name) or name
  if mine(name, kind) then
    ns.Print(L.BOUNTY_ALREADY, label)
    return
  end
  if not (ns.UI and ns.UI.ShowDialog) then
    Bounties.Post(name, gold, max, kind)
    return
  end
  ns.UI.Dialogs.WFG_BOUNTY = ns.UI.Dialogs.WFG_BOUNTY or {
    button1 = L.BOUNTY_CONFIRM_YES,
    button2 = L.BOUNTY_CONFIRM_NO,
    OnAccept = function(_, data) Bounties.Post(data.name, data.gold, data.max, data.kind) end,
  }
  local text = string.format(max > 1 and L.BOUNTY_CONFIRM_MANY or L.BOUNTY_CONFIRM_ONE, gold, label, max, gold * max)
  if guild then text = text .. "\n\n" .. L.BOUNTY_CONFIRM_GUILD end
  ns.UI.ShowDialog("WFG_BOUNTY", text, { name = name, gold = gold, max = max, kind = kind })
end

-- --- cible vue ----------------------------------------------------------------------------------------------

local function alert(entry, seen)
  if not (ns.db and ns.db.settings.bountyAlerts) then return end
  local now = ns.now()
  if now - (entry.alerted or 0) < ns.Data.BOUNTY_ALERT_REPEAT then return end
  entry.alerted = now
  local place = Bounties.Where(entry)
  place = place ~= "" and place or L.WHERE_UNKNOWN
  local target = ns.ClassColored(seen.name or entry.name, seen.class ~= "" and seen.class or entry.class)
  if entry.kind == "g" then target = target .. " <" .. entry.name .. ">" end
  local by = ns.ClassColored(seen.by ~= "" and seen.by or "?", seen.byClass)
  ns.Print(L.BOUNTY_SEEN_CHAT, target, place, by, Bounties.Reward(entry))
  if ns.UI and ns.UI.ShowToast then
    local text = string.format(L.BOUNTY_SEEN_TEXT, target, by)
    local footer = string.format(L.BOUNTY_SEEN_FOOTER, Bounties.Reward(entry), place)
    local label = string.format(L.BOUNTY_SEEN_LOG, seen.name or entry.name, place, seen.by or "?")
    ns.UI.ShowToast(L.BOUNTY_SEEN_HEADER, text, footer, { 1, 0.82, 0 }, ns.db.settings.soundDeaths, "seen:" .. entry.id, label)
  end
end

--- Une observation de la cible (la mienne ou celle d'un guildien) : retenue si elle est plus récente, la pièce
--- d'or suit, le popup au plus une fois par BOUNTY_ALERT_REPEAT s.
local function sighted(entry, seen)
  if entry.seen and (entry.seen.t or 0) >= (seen.t or 0) then return false end
  entry.seen = seen
  if seen.class and seen.class ~= "" then entry.class = seen.class end
  alert(entry, seen)
  if ns.MapUI and ns.MapUI.UpdateBounty then ns.MapUI.UpdateBounty(entry) end
  return true
end

--- Un joueur adverse vient d'être lu (PvE.lua) : s'il porte une prime en cours et que personne ne l'a annoncé
--- depuis BOUNTY_SEEN_DEDUPE s, je l'annonce après un court délai aléatoire, sauf si un guildien me devance.
function Bounties.OnSeen(player, t)
  if not (player and player.player and player.name) then return end
  local entry = Bounties.Match(player.name, player.guild)
  if not entry or pending[entry.id] or ns.InBattleground() then return end
  t = t or ns.now()
  if entry.seen and t - (entry.seen.t or 0) < ns.Data.BOUNTY_SEEN_DEDUPE then return end
  local map, x, y = here()
  local zone, sub = zones()
  local c = ns.char or {}
  local seen = {
    t = t, map = map, x = round4(x), y = round4(y), zone = zone, sub = sub, by = myName(), byClass = c.class,
    name = player.name, class = player.class or "",
  }
  pending[entry.id] = true
  C_Timer.After(math.random() * ns.Data.BOUNTY_SEEN_SPREAD, function()
    ns.Safe("bounties.seen", function()
      pending[entry.id] = nil
      if not Bounties.Open(entry) then return end
      if entry.seen and seen.t - (entry.seen.t or 0) < ns.Data.BOUNTY_SEEN_DEDUPE then return end -- déjà annoncée
      if sighted(entry, seen) then send(Bounties.EncodeSeen(entry, seen)) end
    end)
  end)
end

-- --- kills ----------------------------------------------------------------------------------------------------

--- Un joueur adverse abattu par un membre (moi, ou un « K » ou « H » reçu) : les primes en cours sur ce nom,
--- ou sur sa guilde (`guild` : celle que le chasseur a lue, sinon celle que j'ai lue moi), comptent un kill de
--- plus, une fois par kill (le groupe en envoie autant que de chasseurs). Le kill du commanditaire d'une prime
--- ne compte pas pour elle.
function Bounties.OnKill(name, t, hunterGuid, guild)
  t = t or ns.now()
  if (not guild or guild == "") and ns.SeenPlayerGuild then guild = ns.SeenPlayerGuild(name) end
  local victim = key(name):match("^(%S*)")
  local changed = false
  for _, entry in pairs(table_() or {}) do
    local last = lastKills[entry.id .. "\t" .. victim] or 0
    if Bounties.Open(entry) and targets(entry, name, guild) and t >= (entry.t or 0)
      and not (entry.guid and entry.guid == hunterGuid)
      and math.abs(t - last) >= ns.Data.WANTED_KILL_DEDUPE then
      entry.kills = (entry.kills or 0) + 1
      lastKills[entry.id .. "\t" .. victim] = t
      changed = true
      ns.Print(L.BOUNTY_KILL_CHAT, Bounties.Label(entry), Bounties.Reward(entry), entry.by or "?")
      if not Bounties.Open(entry) and ns.MapUI and ns.MapUI.RemoveBounty then ns.MapUI.RemoveBounty(entry.id) end
    end
  end
  if changed and ns.Nameplates then ns.Nameplates.Refresh() end
end

-- --- échanges entre guildiens ---------------------------------------------------------------------------------

--- Une prime reçue d'un guildien : nouvelle, je la retiens ; connue, je garde le plus grand compte de kills et
--- l'annulation. `live` : elle vient d'être posée, je l'annonce.
function Bounties.Merge(msg)
  local tbl = table_()
  if not tbl then return false end
  local entry = tbl[msg.id]
  if not entry then
    entry = {
      id = msg.id, name = msg.name, gold = msg.gold, max = msg.max, t = msg.t, by = msg.by, byClass = msg.byClass,
      guid = msg.guid, kills = msg.kills or 0, kind = msg.kind,
    }
    if (msg.cancelled or 0) > 0 then entry.cancelled = msg.cancelled end
    tbl[msg.id] = entry
    cap()
    if msg.live and Bounties.Open(entry) then
      ns.Print(L.BOUNTY_NEW_CHAT, ns.ClassColored(entry.by, entry.byClass), Bounties.Label(entry), Bounties.Reward(entry))
    end
    refresh(entry)
    return true
  end
  local changed = false
  if (msg.kills or 0) > (entry.kills or 0) then
    entry.kills = msg.kills
    changed = true
  end
  if (msg.cancelled or 0) > 0 and not entry.cancelled then
    entry.cancelled = msg.cancelled
    changed = true
    ns.Print(L.BOUNTY_CANCELLED_BY, entry.by or "?", Bounties.Label(entry))
  end
  if changed then
    if not Bounties.Open(entry) and ns.MapUI and ns.MapUI.RemoveBounty then ns.MapUI.RemoveBounty(entry.id) end
    if ns.Nameplates then ns.Nameplates.Refresh() end
  end
  return changed
end

--- Demande les primes aux guildiens connectés (à la connexion).
function Bounties.Request()
  send("B\t1")
end

--- Les primes à redire à un membre qui se connecte : celles en cours, puis les annulées (pour qu'il les ferme).
function Bounties.Digest()
  local lines = {}
  for _, entry in ipairs(Bounties.Sorted(true)) do
    if #lines >= ns.Data.BOUNTY_DIGEST_MAX then break end
    if Bounties.Open(entry) or entry.cancelled then lines[#lines + 1] = Bounties.Encode(entry, false) end
  end
  return lines
end

local function answerRequest()
  local before = digests
  local lines = Bounties.Digest()
  if #lines == 0 then return end
  C_Timer.After(1 + math.random() * ns.Data.WANTED_ANSWER_SPREAD, function()
    if digests ~= before then
      ns.Trace("demande B : quelqu'un a déjà répondu")
      return
    end
    for _, line in ipairs(lines) do send(line) end
    digests = digests + 1 -- ma réponse vaut pour les demandes en attente (l'écho n'en rajoutera pas)
  end)
end

local function onAddonMessage(prefix, text, channel, sender)
  if ns.plain(prefix) ~= ns.Data.ADDON_PREFIX or ns.plain(channel) ~= "GUILD" then return end
  text, sender = ns.plain(text), ns.plain(sender)
  if type(text) ~= "string" then return end
  local kind = text:sub(1, 1)
  if kind == "B" then
    local msg = Bounties.Decode(text)
    if not msg then return end
    if msg.request then
      ns.Trace("reçu B de %s : demande des primes", tostring(sender))
      answerRequest()
      return
    end
    if not msg.live then digests = digests + 1 end
    local ok, changed = pcall(Bounties.Merge, msg)
    if not ok then ns.Store.LogError("bounties.merge", changed) end
    ns.Trace("reçu B de %s : prime sur %s%s", tostring(sender), msg.name, (ok and changed) and "" or " (déjà connue)")
  elseif kind == "S" then
    local msg = Bounties.DecodeSeen(text)
    if not msg then return end
    local entry = (table_() or {})[msg.id]
    if not entry or not Bounties.Open(entry) then return end
    ns.Trace("reçu S de %s : %s vu", tostring(sender), msg.name)
    ns.Safe("bounties.seen", sighted, entry, {
      t = msg.t, map = msg.map, x = msg.x, y = msg.y, zone = msg.zone, sub = msg.sub, by = msg.by, byClass = msg.byClass,
      name = msg.name ~= "" and msg.name or entry.name, class = msg.class,
    })
  end
end

-- --- export, carte ----------------------------------------------------------------------------------------------

--- Les primes posées en jeu que je connais, pour le site : les miennes et celles reçues des guildiens (le site
--- reconnaît le commanditaire par son personnage). Celles venues du site n'y retournent pas.
function Bounties.Export()
  local out = ns.Json.array()
  local list = Bounties.Sorted(true)
  table.sort(list, function(a, b) return (a.t or 0) > (b.t or 0) end)
  for _, entry in ipairs(list) do
    if #out >= ns.Data.BOUNTY_EXPORT_MAX then break end
    if entry.guid and entry.guid ~= "" then
      out[#out + 1] = {
        id = entry.id, guid = entry.guid, name = entry.name, gold = entry.gold, max = entry.max, t = entry.t,
        cancelled = entry.cancelled, kind = entry.kind,
      }
    end
  end
  return out
end

--- Toutes les 10 s : la pièce d'or pâlit puis disparaît au bout de BOUNTY_SEEN_TTL s.
function Bounties.Tick()
  if not (ns.MapUI and ns.MapUI.UpdateBounty) then return end
  local now = ns.now()
  for id, entry in pairs(table_() or {}) do
    if Bounties.Open(entry) and Bounties.Fresh(entry, now) then ns.MapUI.UpdateBounty(entry) else ns.MapUI.RemoveBounty(id) end
  end
end

--- Case « Alertes de primes » : décochée, plus de popup ni de pièce sur la carte.
function Bounties.SetAlerts(on)
  ns.db.settings.bountyAlerts = on and true or false
  Bounties.Tick()
end

ns.RegisterCollector({
  name = "bounties",
  events = { CHAT_MSG_ADDON = true },
  onLogin = function()
    C_Timer.After(6, function() ns.Safe("bounties.tick", Bounties.Tick) end)
    C_Timer.After(ns.Data.BOUNTY_HANDSHAKE_DELAY, function() ns.Safe("bounties.request", Bounties.Request) end)
    C_Timer.NewTicker(ns.Data.POSITION_TICK, function() ns.Safe("bounties.tick", Bounties.Tick) end)
  end,
  onEvent = function(_, _, ...)
    onAddonMessage(...)
  end,
  status = function()
    local open, all = 0, 0
    for _, entry in pairs(table_() or {}) do
      all = all + 1
      if Bounties.Open(entry) then open = open + 1 end
    end
    return string.format("%d prime(s) en cours · %d connue(s)", open, all)
  end,
})
