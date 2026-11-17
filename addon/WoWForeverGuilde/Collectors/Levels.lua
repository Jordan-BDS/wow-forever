-- Montées de niveau, en jeu seulement : message addon (préfixe WFG, type « N ») sur le canal de guilde à
-- PLAYER_LEVEL_UP, lu par les autres addons, popup flottant chez ceux qui l'affichent (« Afficher les montées de
-- niveau des autres »), sans son. Noté dans l'historique de /mf, popup coché ou non. Ma propre montée n'a pas de
-- popup chez moi (le jeu l'annonce déjà) : son écho la note seulement dans mon historique.
-- Ligne « N » : guid, prénom, nom, classe (jeton), niveau, zone, heure. Les versions d'avant l'ignorent.
-- Le niveau est celui de l'événement : sur Forever, UnitLevel("player") peut rester sur l'ancien (cf. Identity.lua).
-- /mf niveau [n] joue le popup chez soi sans rien envoyer ni noter.
local ADDON, ns = ...

ns.Levels = {}
local Levels = ns.Levels

local function encodeField(s)
  return (tostring(s or ""):gsub("[\t\n]", " "))
end

local function parse(line)
  local prefix = ns.Data.LEVEL_PREFIX
  if line:sub(1, #prefix) ~= prefix then return nil end
  local fields = {}
  for field in (line:sub(#prefix + 1) .. "\t"):gmatch("([^\t]*)\t") do fields[#fields + 1] = field end
  local level = tonumber(fields[5])
  if #fields < 5 or fields[1] == "" or fields[2] == "" or not level or level < 2 then return nil end
  return {
    guid = fields[1], name = fields[2], surname = fields[3], class = fields[4], level = math.floor(level),
    zone = fields[6] or "", t = tonumber(fields[7]),
  }
end
Levels.Parse = parse

--- Phrase d'une montée de niveau, prête à afficher, le personnage à la couleur de sa classe. La graine : qui et
--- quel niveau, portés par le message. Tous les guildiens tirent la même phrase.
function Levels.Phrase(info)
  local roles = { personnage = ns.Phrases.Role(ns.DeathName(info), info.class), niveau = tostring(info.level) }
  local seed = "N:" .. tostring(info.guid) .. ":" .. tostring(info.level)
  return ns.Phrases.Fill(ns.Phrases.Pick(ns.LEVEL_PHRASES, "{personnage} passe niveau {niveau}.", seed), roles)
end

local function myInfo(char, level)
  local class = char.class
  if type(class) ~= "string" or class == "" then
    local ok, _, token = pcall(UnitClass, "player")
    class = ok and ns.plain(token) or ""
  end
  local ok, zone = pcall(GetZoneText)
  zone = ok and ns.plain(zone) or ""
  return {
    guid = char.guid, name = char.name, surname = char.surname, class = class, level = level,
    zone = type(zone) == "string" and zone or "", t = ns.now(),
  }
end

local function announce(char, level)
  if not ns.db.settings.announceLevels then return end
  if not (IsInGuild and IsInGuild()) then return end
  local api = (C_ChatInfo and C_ChatInfo.SendAddonMessage) or SendAddonMessage
  if not api then return end
  local info = myInfo(char, level)
  local fields = {
    encodeField(info.guid), encodeField(info.name), encodeField(info.surname), encodeField(info.class),
    tostring(info.level), encodeField(info.zone), tostring(info.t),
  }
  local line = ns.Data.LEVEL_PREFIX .. table.concat(fields, "\t")
  if #line > 255 then
    fields[6] = ""
    line = ns.Data.LEVEL_PREFIX .. table.concat(fields, "\t")
  end
  if #line > 255 then return end
  local ok, result = ns.Risky("SendAddonMessage GUILD (niveau)", pcall, api, ns.Data.ADDON_PREFIX, line, "GUILD")
  ns.Trace("envoi N (niveau %d) → %s", info.level, (ok and (result == nil or result == true or result == 0)) and "accepté" or tostring(result))
end

--- /mf niveau [n] : joue le popup chez soi pour son personnage (son niveau, ou `n`), sans rien envoyer ni noter.
function Levels.Rehearse(raw)
  local char = ns.char
  if not char or not ns.UI or not ns.UI.ShowLevel then return end
  local level = tonumber((raw or ""):match("%d+")) or char.level or 1
  local info = myInfo(char, math.max(2, math.floor(level)))
  ns.UI.ShowLevel(info, Levels.Phrase(info), false, true)
end

ns.RegisterCollector({
  name = "levels",
  events = { PLAYER_LEVEL_UP = true, CHAT_MSG_ADDON = true },
  onEvent = function(char, event, ...)
    if event == "PLAYER_LEVEL_UP" then
      local level = tonumber(ns.plain((...)))
      if level and level >= 2 then announce(char, math.floor(level)) end
      return
    end
    local prefix, text, channel = ...
    if ns.plain(prefix) ~= ns.Data.ADDON_PREFIX or ns.plain(channel) ~= "GUILD" then return end
    text = ns.plain(text)
    if type(text) ~= "string" then return end
    local info = parse(text)
    if not info then return end
    local mine = char ~= nil and info.guid == char.guid
    local quiet = mine or not ns.db.settings.showLevels
    ns.Trace("niveau %d de %s reçu : %s", info.level, info.name,
      mine and "le mien, historique seul" or (quiet and "popup désactivé dans les réglages" or "popup"))
    if ns.UI and ns.UI.ShowLevel then ns.UI.ShowLevel(info, Levels.Phrase(info), quiet) end
  end,
})
