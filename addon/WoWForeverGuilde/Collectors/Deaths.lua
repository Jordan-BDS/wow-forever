-- Annonces de mort, en jeu seulement : ligne balisée dans un canal caché lue par les autres addons, popup flottant
-- 5 s avec son chez ceux qui l'affichent. Rien dans le canal de guilde, rien vers Discord.
local ADDON, ns = ...

local channelName = ns.Data.DEATH_CHANNEL
local joined = false

local function hideChannel()
  for i = 1, (NUM_CHAT_WINDOWS or 10) do
    local frame = _G["ChatFrame" .. i]
    if frame and ChatFrame_RemoveChannel then pcall(ChatFrame_RemoveChannel, frame, channelName) end
  end
end

local function join()
  if joined or not JoinChannelByName then return end
  local ok = pcall(JoinChannelByName, channelName, ns.Data.DEATH_CHANNEL_PASSWORD, nil, false)
  joined = ok and true or false
  hideChannel()
end

local function channelIndex()
  if not GetChannelName then return nil end
  local id = GetChannelName(channelName)
  return id and id > 0 and id or nil
end

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
  local index = channelIndex()
  if not index or not SendChatMessage then return end
  local className = UnitClass("player")
  local line = ns.Data.DEATH_PREFIX .. table.concat({
    encodeField(char.guid), encodeField(char.name), encodeField(char.surname), encodeField(className or char.class),
    tostring(char.level or 0), encodeField(describeKiller(death)), encodeField(death.zone), encodeField(death.sub),
    tostring(death.t or ns.now()),
  }, "\t")
  if #line <= 255 then SendChatMessage(line, "CHANNEL", nil, index) end
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
  return (phrase:gsub("{(%w+)}", function(key) return values[key] or ("{" .. key .. "}") end))
end

ns.RegisterCollector({
  name = "deaths",
  events = { CHAT_MSG_CHANNEL = true, CHANNEL_UI_UPDATE = true, PLAYER_ENTERING_WORLD = true },
  onLogin = function()
    C_Timer.After(5, join)
  end,
  onEvent = function(char, event, ...)
    if event == "PLAYER_ENTERING_WORLD" or event == "CHANNEL_UI_UPDATE" then
      if joined then hideChannel() end
    elseif event == "CHAT_MSG_CHANNEL" then
      local text, _, _, _, _, _, _, _, name = ...
      text = ns.plain(text)
      if type(text) ~= "string" or type(name) ~= "string" or name:lower() ~= channelName then return end
      local info = parse(text)
      if not info or not ns.db.settings.showDeaths then return end
      if ns.UI and ns.UI.ShowDeath then ns.UI.ShowDeath(info, ns.DeathPhrase(info)) end
    end
  end,
})
