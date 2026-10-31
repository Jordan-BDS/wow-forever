-- Partage de position entre membres. Quand « Partager ma position » est coché, le client émet sa carte, ses
-- coordonnées, son niveau et un résumé de talents par message addon (canal de guilde, ou canal caché tant que la
-- guilde n'existe pas) ; les autres l'affichent sur la carte du monde (MapUI.lua). Règle symétrique : ne pas
-- partager = ne pas voir. Envoi au changement de zone, au déplacement, et au moins toutes les POSITION_HEARTBEAT s.
local ADDON, ns = ...

local Positions = { peers = {} }
ns.Positions = Positions

local PREFIX = ns.Data.ADDON_PREFIX
local last = { at = 0 }
local registered = false
local scheduled = false

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

--- Ligne « P » : position. Les champs longs (sous-zone, talents, zone) sautent si la ligne dépasse 255 octets.
function Positions.Encode(char, map, x, y)
  local class = char.class or (UnitClass and select(2, UnitClass("player"))) or ""
  local fields = {
    "P", "1", field(char.guid), field(displayName(char)), field(class),
    tostring((UnitLevel and UnitLevel("player")) or char.level or 0),
    map and tostring(map) or "", x and string.format("%.4f", x) or "", y and string.format("%.4f", y) or "",
    field(GetZoneText and GetZoneText() or ""), field(GetSubZoneText and GetSubZoneText() or ""),
    field(ns.TalentSummary and ns.TalentSummary() or ""),
  }
  local line = table.concat(fields, "\t")
  for _, i in ipairs({ 11, 12, 10 }) do
    if #line <= 255 then break end
    fields[i] = ""
    line = table.concat(fields, "\t")
  end
  return line:sub(1, 255)
end

function Positions.EncodeLeave(char)
  return table.concat({ "L", "1", field(char.guid) }, "\t")
end

function Positions.Decode(text)
  local fields = {}
  for f in (text .. "\t"):gmatch("([^\t]*)\t") do fields[#fields + 1] = f end
  if fields[2] ~= "1" then return nil end
  if fields[1] == "L" then return fields[3] and { kind = "L", guid = fields[3] } or nil end
  if fields[1] ~= "P" or #fields < 12 or fields[3] == "" then return nil end
  return {
    kind = "P", guid = fields[3], name = fields[4], class = fields[5], level = tonumber(fields[6]) or 0,
    map = tonumber(fields[7]), x = tonumber(fields[8]), y = tonumber(fields[9]),
    zone = fields[10], sub = fields[11], spec = fields[12],
  }
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

-- --- réception ------------------------------------------------------------------------------------------

function Positions.Forget(guid)
  if not Positions.peers[guid] then return end
  Positions.peers[guid] = nil
  if ns.MapUI then ns.MapUI.Remove(guid) end
end

function Positions.ForgetAll()
  for guid in pairs(Positions.peers) do Positions.peers[guid] = nil end
  if ns.MapUI then ns.MapUI.Clear() end
end

local function onAddonMessage(prefix, text, _, sender)
  if prefix ~= PREFIX or not enabled() then return end
  text, sender = ns.plain(text), ns.plain(sender)
  if type(text) ~= "string" then return end
  local msg = Positions.Decode(text)
  if not msg or (ns.char and msg.guid == ns.char.guid) then return end
  if msg.kind == "L" then Positions.Forget(msg.guid) return end
  msg.sender = type(sender) == "string" and sender ~= "" and sender or msg.name
  msg.at = ns.now()
  Positions.peers[msg.guid] = msg
  if ns.MapUI then ns.MapUI.Update(msg) end
end

local function prune()
  local limit = ns.now() - ns.Data.POSITION_TTL
  for guid, peer in pairs(Positions.peers) do
    if (peer.at or 0) < limit then Positions.Forget(guid) end
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
    ns.Print(ns.L.POSITION_ON)
  else
    if ns.char then send(Positions.EncodeLeave(ns.char)) end
    Positions.ForgetAll()
    ns.Print(ns.L.POSITION_OFF)
  end
end

ns.RegisterCollector({
  name = "positions",
  events = {
    CHAT_MSG_ADDON = true, ZONE_CHANGED_NEW_AREA = true, ZONE_CHANGED = true, ZONE_CHANGED_INDOORS = true,
    PLAYER_ENTERING_WORLD = true,
  },
  onLogin = function()
    registerPrefix()
    C_Timer.After(6, function() ns.Safe("positions.broadcast", broadcast, true) end) -- après le canal caché (5 s)
    C_Timer.NewTicker(ns.Data.POSITION_TICK, function() ns.Safe("positions.tick", tick) end)
  end,
  onEvent = function(_, event, ...)
    if event == "CHAT_MSG_ADDON" then
      onAddonMessage(...)
    else
      scheduleBroadcast()
    end
  end,
  onLogout = function(char)
    if enabled() then send(Positions.EncodeLeave(char)) end
  end,
})
