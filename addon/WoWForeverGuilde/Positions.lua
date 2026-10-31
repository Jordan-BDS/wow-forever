-- Partage de position entre membres. Quand « Partager ma position » est coché, le client émet sa carte, ses
-- coordonnées, son niveau, un résumé de talents et son éventuelle recherche de groupe par message addon (canal de
-- guilde, ou canal caché tant que la guilde n'existe pas) ; les autres l'affichent sur la carte du monde (MapUI.lua)
-- et dans la liste « Guilde en jeu » (RosterUI.lua). Règle symétrique : ne pas partager = ne pas voir.
-- Envoi au changement de zone, au déplacement, et au moins toutes les POSITION_HEARTBEAT s.
-- Appel à l'aide (« gank ») : détecté dans le journal de combat (joueur hostile qui me frappe, hors instance et hors
-- duel) ou par /wfg sos ; un envoi par GANK_COOLDOWN s ; chez les autres, toast et son dans la même zone, ligne de
-- chat ailleurs, anneau rouge sur le point pendant ALERT_TTL s.
local ADDON, ns = ...

local Positions = { peers = {}, lfg = nil }
ns.Positions = Positions
local L = ns.L

local PREFIX = ns.Data.ADDON_PREFIX
local last = { at = 0 }
local lastSOS = 0
local registered = false
local scheduled = false
local dueling = false

local function enabled()
  return ns.db ~= nil and ns.db.settings.sharePosition == true
end
Positions.Enabled = enabled

local function registerPrefix()
  if registered then return end
  local reg = (C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix) or RegisterAddonMessagePrefix
  if reg then pcall(reg, PREFIX) end
  registered = true
end

--- Nom coloré par classe (balise de couleur du client).
function ns.ClassColored(name, class)
  local c = RAID_CLASS_COLORS and class and RAID_CLASS_COLORS[class]
  return "|c" .. ((c and c.colorStr) or "ffffffff") .. (name or "?") .. "|r"
end

--- Zone et sous-zone lisibles d'un membre.
function Positions.Where(peer)
  local text = peer.zone or ""
  if peer.sub and peer.sub ~= "" and peer.sub ~= peer.zone then
    text = text ~= "" and (text .. " · " .. peer.sub) or peer.sub
  end
  return text
end

--- Carte et coordonnées (fractions 0-1) du joueur. Carte seule en instance ou quand le client ne les donne pas.
function Positions.Here()
  if not (C_Map and C_Map.GetBestMapForUnit and C_Map.GetPlayerMapPosition) then return nil end
  local map = ns.plain(C_Map.GetBestMapForUnit("player"))
  if not map then return nil end
  local pos = C_Map.GetPlayerMapPosition(map, "player")
  if not pos then return map end
  local x, y = pos.x, pos.y
  if x == nil and pos.GetXY then x, y = pos:GetXY() end
  x, y = ns.plain(x), ns.plain(y)
  if type(x) ~= "number" or type(y) ~= "number" or (x == 0 and y == 0) then return map end
  return map, x, y
end

-- --- messages -----------------------------------------------------------------------------------------

local function field(s)
  return (tostring(s or ""):gsub("[\t\n]", " "))
end

-- Nom affiché : prénom et nom de famille (Forever), comme le lit le collecteur d'identité.
local function displayName(char)
  local full = UnitFullName and ns.plain((UnitFullName("player")))
  if type(full) == "string" and full ~= "" then return full end
  local name = char.name or (UnitName and UnitName("player")) or "?"
  if char.surname and char.surname ~= "" then name = name .. " " .. char.surname end
  return name
end

local function baseFields(kind, char, map, x, y)
  local class = char.class or (UnitClass and select(2, UnitClass("player"))) or ""
  return {
    kind, "1", field(char.guid), field(displayName(char)), field(class),
    tostring((UnitLevel and UnitLevel("player")) or char.level or 0),
    map and tostring(map) or "", x and string.format("%.4f", x) or "", y and string.format("%.4f", y) or "",
    field(GetZoneText and GetZoneText() or ""), field(GetSubZoneText and GetSubZoneText() or ""),
  }
end

-- Au-delà de 255 octets, les champs longs sautent dans cet ordre (sous-zone, puis talents/agresseur, puis zone).
local function pack(fields)
  local line = table.concat(fields, "\t")
  for _, i in ipairs({ 11, 12, 10 }) do
    if #line <= 255 then break end
    fields[i] = ""
    line = table.concat(fields, "\t")
  end
  return line:sub(1, 255)
end

--- Ligne « P » : position, résumé de talents, recherche de groupe.
function Positions.Encode(char, map, x, y)
  local fields = baseFields("P", char, map, x, y)
  fields[12] = field(ns.TalentSummary and ns.TalentSummary() or "")
  fields[13] = field(Positions.lfg or "")
  return pack(fields)
end

--- Ligne « G » : appel à l'aide, avec la position et l'agresseur s'il est connu.
function Positions.EncodeAlert(char, map, x, y, attacker, attackerClass)
  local fields = baseFields("G", char, map, x, y)
  fields[12] = field(attacker or "")
  fields[13] = field(attackerClass or "")
  return pack(fields)
end

function Positions.EncodeLeave(char)
  return table.concat({ "L", "1", field(char.guid) }, "\t")
end

function Positions.Decode(text)
  local fields = {}
  for f in (text .. "\t"):gmatch("([^\t]*)\t") do fields[#fields + 1] = f end
  if fields[2] ~= "1" then return nil end
  local kind = fields[1]
  if kind == "L" then return fields[3] and fields[3] ~= "" and { kind = "L", guid = fields[3] } or nil end
  if (kind ~= "P" and kind ~= "G") or #fields < 12 or fields[3] == "" then return nil end
  local msg = {
    kind = kind, guid = fields[3], name = fields[4], class = fields[5], level = tonumber(fields[6]) or 0,
    map = tonumber(fields[7]), x = tonumber(fields[8]), y = tonumber(fields[9]),
    zone = fields[10], sub = fields[11],
  }
  if kind == "P" then
    msg.spec, msg.lfg = fields[12], fields[13] or ""
  else
    msg.attacker, msg.attackerClass = fields[12], fields[13] or ""
  end
  return msg
end

-- --- transport ----------------------------------------------------------------------------------------

local function send(text)
  local api = (C_ChatInfo and C_ChatInfo.SendAddonMessage) or SendAddonMessage
  if not api then return false end
  if IsInGuild and IsInGuild() then return (pcall(api, PREFIX, text, "GUILD")) end
  local index = ns.HiddenChannelIndex and ns.HiddenChannelIndex()
  if index then return (pcall(api, PREFIX, text, "CHANNEL", index)) end
  return false
end

local function moved(map, x, y, zone)
  if map ~= last.map or zone ~= last.zone then return true end
  if (x == nil) ~= (last.x == nil) then return true end
  if x == nil then return false end
  return math.abs(x - last.x) + math.abs(y - last.y) >= ns.Data.POSITION_MOVE_THRESHOLD
end

local function broadcast(force)
  if not enabled() or not ns.char then return end
  local map, x, y = Positions.Here()
  local zone = (GetZoneText and GetZoneText()) or ""
  local t = ns.now()
  if not (force or moved(map, x, y, zone) or t - last.at >= ns.Data.POSITION_HEARTBEAT) then return end
  if send(Positions.Encode(ns.char, map, x, y)) then
    last.at, last.map, last.x, last.y, last.zone = t, map, x, y, zone
  end
end
Positions.Broadcast = broadcast

-- Changement de zone : un seul envoi 2 s plus tard, même si plusieurs événements arrivent (et même en combat).
local function scheduleBroadcast()
  if scheduled then return end
  scheduled = true
  C_Timer.After(2, function()
    scheduled = false
    ns.Safe("positions.broadcast", broadcast, true)
  end)
end

--- /wfg lfg <texte> : recherche de groupe diffusée avec la position ; vide pour retirer.
function Positions.SetLFG(text)
  text = (text or ""):gsub("^%s+", ""):gsub("%s+$", "")
  Positions.lfg = text ~= "" and text:sub(1, 60) or nil
  if enabled() then
    last.at = 0
    broadcast(true)
  end
  if Positions.lfg then ns.Print(L.LFG_SET, Positions.lfg) else ns.Print(L.LFG_CLEARED) end
  if ns.RosterUI then ns.RosterUI.Refresh() end
end

-- --- appel à l'aide ----------------------------------------------------------------------------------------

local TYPE_PLAYER, REACTION_HOSTILE = 0x400, 0x40
local function hasFlag(flags, flag)
  return type(flags) == "number" and math.floor(flags / flag) % 2 == 1
end

--- Envoie l'appel. `attacker`/`attackerGUID` viennent du journal de combat ; en manuel (/wfg sos), la cible si
--- c'est un joueur. Un envoi par GANK_COOLDOWN s.
function Positions.SOS(attacker, attackerGUID, manual)
  if not ns.char then return false end
  if not enabled() then
    if manual then ns.Print(L.SOS_NEEDS_SHARING) end
    return false
  end
  local t = ns.now()
  if t - lastSOS < ns.Data.GANK_COOLDOWN then return false end
  local class = ""
  if attackerGUID and GetPlayerInfoByGUID then
    local _, token = GetPlayerInfoByGUID(attackerGUID)
    class = ns.plain(token) or ""
  end
  if manual and not attacker and UnitExists and UnitExists("target") and UnitIsPlayer and UnitIsPlayer("target") then
    attacker = ns.plain(UnitName("target"))
    class = ns.plain(select(2, UnitClass("target"))) or ""
  end
  local map, x, y = Positions.Here()
  if not send(Positions.EncodeAlert(ns.char, map, x, y, attacker, class)) then return false end
  lastSOS = t
  if manual then ns.Print(L.SOS_SENT) end
  return true
end

local function onCombatLog()
  if not CombatLogGetCurrentEventInfo or not ns.char or dueling then return end
  local _, subevent, _, sourceGUID, sourceName, sourceFlags, _, destGUID = CombatLogGetCurrentEventInfo()
  if ns.plain(destGUID) ~= ns.char.guid then return end
  subevent = ns.plain(subevent)
  if type(subevent) ~= "string" or not subevent:find("_DAMAGE$") then return end
  sourceGUID, sourceFlags = ns.plain(sourceGUID), ns.plain(sourceFlags)
  if sourceGUID == ns.char.guid or not (hasFlag(sourceFlags, TYPE_PLAYER) and hasFlag(sourceFlags, REACTION_HOSTILE)) then
    return
  end
  if IsInInstance and IsInInstance() then return end -- champs de bataille, arènes, donjons
  Positions.SOS(ns.plain(sourceName), sourceGUID, false)
end

local function announceAlert(peer)
  if not ns.db.settings.gankAlerts then return end
  local attacker = peer.alert.attacker ~= "" and ns.ClassColored(peer.alert.attacker, peer.alert.class) or L.ATTACKER_UNKNOWN
  local place = Positions.Where(peer)
  local text = string.format(L.ALERT_TEXT, ns.ClassColored(peer.name, peer.class), attacker, place ~= "" and place or L.WHERE_UNKNOWN)
  ns.Print(text)
  local myMap = Positions.Here()
  if myMap and peer.map == myMap and ns.UI and ns.UI.ShowAlert then ns.UI.ShowAlert(peer, text) end
end

-- --- réception ------------------------------------------------------------------------------------------

function Positions.Forget(guid)
  if not Positions.peers[guid] then return end
  Positions.peers[guid] = nil
  if ns.MapUI then ns.MapUI.Remove(guid) end
  if ns.RosterUI then ns.RosterUI.Refresh() end
end

function Positions.ForgetAll()
  for guid in pairs(Positions.peers) do Positions.peers[guid] = nil end
  if ns.MapUI then ns.MapUI.Clear() end
  if ns.RosterUI then ns.RosterUI.Refresh() end
end

local function onAddonMessage(prefix, text, _, sender)
  if prefix ~= PREFIX or not enabled() then return end
  text, sender = ns.plain(text), ns.plain(sender)
  if type(text) ~= "string" then return end
  local msg = Positions.Decode(text)
  if not msg or (ns.char and msg.guid == ns.char.guid) then return end
  if msg.kind == "L" then Positions.Forget(msg.guid) return end
  local peer = Positions.peers[msg.guid] or {}
  local previous = peer.alert
  for key, value in pairs(msg) do peer[key] = value end
  peer.kind = nil
  peer.sender = type(sender) == "string" and sender ~= "" and sender or msg.name
  peer.at = ns.now()
  if msg.kind == "G" then
    peer.alert = { at = peer.at, attacker = msg.attacker or "", class = msg.attackerClass or "" }
    peer.attacker, peer.attackerClass = nil, nil
  else
    peer.alert = previous
  end
  Positions.peers[msg.guid] = peer
  if ns.MapUI then ns.MapUI.Update(peer) end
  if ns.RosterUI then ns.RosterUI.Refresh() end
  if msg.kind == "G" then announceAlert(peer) end
end

local function prune()
  local now = ns.now()
  for guid, peer in pairs(Positions.peers) do
    if (peer.at or 0) < now - ns.Data.POSITION_TTL then
      Positions.Forget(guid)
    elseif peer.alert and peer.alert.at < now - ns.Data.ALERT_TTL then
      peer.alert = nil
      if ns.MapUI then ns.MapUI.Update(peer) end
    end
  end
end

local function tick()
  prune()
  broadcast(false)
end

--- Case « Partager ma position » : coché → on émet tout de suite ; décoché → on prévient et on efface la carte.
function Positions.SetSharing(on)
  on = on and true or false
  if ns.db.settings.sharePosition == on then return end
  ns.db.settings.sharePosition = on
  if on then
    registerPrefix()
    last.at = 0
    broadcast(true)
    ns.Print(L.POSITION_ON)
  else
    if ns.char then send(Positions.EncodeLeave(ns.char)) end
    Positions.ForgetAll()
    ns.Print(L.POSITION_OFF)
  end
end

-- --- membres en ligne (roster + positions) ------------------------------------------------------------------

local function shortName(name)
  name = (name or ""):gsub("%-.*$", "")
  return (name:match("^(%S+)") or name):lower()
end

--- Membres en ligne d'après le roster de guilde, enrichis des positions reçues ; membres sans roster (canal caché)
--- ajoutés à part. Chaque entrée : name (affiché), sender (pour inviter/chuchoter), level, class, zone, guid, peer.
function Positions.Members()
  local list, byGuid, byName = {}, {}, {}
  if GetNumGuildMembers and GetGuildRosterInfo then
    for i = 1, (ns.plain(GetNumGuildMembers()) or 0) do
      local name, _, _, level, _, zone, _, _, online, _, classFile, _, _, _, _, _, guid = GetGuildRosterInfo(i)
      name = ns.plain(name)
      if type(name) == "string" and ns.plain(online) then
        local m = {
          name = (name:gsub("%-.*$", "")), sender = name, level = ns.plain(level) or 0, class = ns.plain(classFile),
          zone = ns.plain(zone) or "", guid = ns.plain(guid), roster = true,
        }
        list[#list + 1] = m
        if m.guid then byGuid[m.guid] = m end
        byName[shortName(name)] = m
      end
    end
  end
  for guid, peer in pairs(Positions.peers) do
    local m = byGuid[guid] or byName[shortName(peer.sender)] or byName[shortName(peer.name)]
    if m then
      m.peer = peer
      m.name = peer.name ~= "" and peer.name or m.name
      if peer.zone ~= "" then m.zone = peer.zone end
      if peer.level > 0 then m.level = peer.level end
      if peer.class ~= "" then m.class = peer.class end
    else
      list[#list + 1] = {
        name = peer.name, sender = peer.sender, level = peer.level, class = peer.class, zone = peer.zone or "",
        guid = guid, peer = peer,
      }
    end
  end
  return list
end

ns.RegisterCollector({
  name = "positions",
  events = {
    CHAT_MSG_ADDON = true, ZONE_CHANGED_NEW_AREA = true, ZONE_CHANGED = true, ZONE_CHANGED_INDOORS = true,
    PLAYER_ENTERING_WORLD = true, COMBAT_LOG_EVENT_UNFILTERED = true, DUEL_REQUESTED = true, DUEL_FINISHED = true,
    GUILD_ROSTER_UPDATE = true,
  },
  onLogin = function()
    registerPrefix()
    C_Timer.After(6, function() ns.Safe("positions.broadcast", broadcast, true) end) -- après le canal caché (5 s)
    C_Timer.NewTicker(ns.Data.POSITION_TICK, function() ns.Safe("positions.tick", tick) end)
  end,
  onEvent = function(_, event, ...)
    if event == "CHAT_MSG_ADDON" then
      onAddonMessage(...)
    elseif event == "COMBAT_LOG_EVENT_UNFILTERED" then
      onCombatLog()
    elseif event == "DUEL_REQUESTED" then
      dueling = true
    elseif event == "DUEL_FINISHED" then
      dueling = false
    elseif event == "GUILD_ROSTER_UPDATE" then
      if ns.RosterUI then ns.RosterUI.Refresh() end
    else
      scheduleBroadcast()
    end
  end,
  onLogout = function(char)
    if enabled() then send(Positions.EncodeLeave(char)) end
  end,
})
