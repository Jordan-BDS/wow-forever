-- Annonces de mort, en jeu seulement : message addon (préfixe WFG, type « D ») sur le canal de guilde, lu par les
-- autres addons, popup flottant 5 s avec son chez ceux qui l'affichent. Rien de visible dans le chat, rien vers
-- Discord. Le client moderne interdit aux addons les canaux de chat : pas de canal caché, il faut une guilde.
local ADDON, ns = ...

local function describeKiller(death)
  if death.env and ns.Data.ENVIRONMENTAL[death.env] then return ns.L[ns.Data.ENVIRONMENTAL[death.env]] end
  if death.killer and death.killer ~= "" then return death.killer end
  return ns.L.KILLER_UNKNOWN
end

local function encodeField(s)
  return (tostring(s or ""):gsub("[\t\n]", " "))
end

--- Appelé par le collecteur PvE à PLAYER_DEAD.
function ns.OnDeath(char, death)
  if not ns.db.settings.announceDeaths then return end
  if not (IsInGuild and IsInGuild()) then return end
  local api = (C_ChatInfo and C_ChatInfo.SendAddonMessage) or SendAddonMessage
  if not api then return end
  local className = UnitClass("player")
  local line = ns.Data.DEATH_PREFIX .. table.concat({
    encodeField(char.guid), encodeField(char.name), encodeField(char.surname), encodeField(className or char.class),
    tostring(char.level or 0), encodeField(describeKiller(death)), encodeField(death.zone), encodeField(death.sub),
    tostring(death.t or ns.now()),
  }, "\t")
  if #line <= 255 then pcall(api, ns.Data.ADDON_PREFIX, line, "GUILD") end
end

local function parse(line)
  if line:sub(1, #ns.Data.DEATH_PREFIX) ~= ns.Data.DEATH_PREFIX then return nil end
  local fields = {}
  for field in (line:sub(#ns.Data.DEATH_PREFIX + 1) .. "\t"):gmatch("([^\t]*)\t") do fields[#fields + 1] = field end
  if #fields < 9 then return nil end
  return {
    guid = fields[1], name = fields[2], surname = fields[3], class = fields[4], level = tonumber(fields[5]) or 0,
    killer = fields[6], zone = fields[7], sub = fields[8], t = tonumber(fields[9]),
  }
end
ns.ParseDeathLine = parse

function ns.DeathPhrase(info)
  local phrases = ns.PHRASES
  local phrase = phrases[math.random(1, #phrases)]
  local zone = info.zone ~= "" and info.zone or info.sub
  local values = {
    personnage = info.name, tueur = info.killer, zone = zone ~= "" and zone or "nulle part", niveau = tostring(info.level),
    classe = info.class,
  }
  local text = phrase:gsub("{(%w+)}", function(key) return values[key] or ("{" .. key .. "}") end)
  return (text:gsub("^%l", string.upper)) -- « une chute remercie… » → « Une chute remercie… »
end

ns.RegisterCollector({
  name = "deaths",
  events = { CHAT_MSG_ADDON = true },
  onEvent = function(char, event, prefix, text, channel)
    if ns.plain(prefix) ~= ns.Data.ADDON_PREFIX or ns.plain(channel) ~= "GUILD" then return end
    text = ns.plain(text)
    if type(text) ~= "string" then return end
    local info = parse(text)
    if not info or not ns.db.settings.showDeaths then return end
    if ns.UI and ns.UI.ShowDeath then ns.UI.ShowDeath(info, ns.DeathPhrase(info)) end
  end,
})
