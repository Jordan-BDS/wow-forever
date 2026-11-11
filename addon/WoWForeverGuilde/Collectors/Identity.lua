-- Identité : nom complet, royaume, classe, race, niveau, temps de jeu (opt-in), montées de niveau horodatées.
local ADDON, ns = ...

-- Le niveau ne redescend jamais : sur Forever, UnitLevel("player") peut rester sur l'ancien niveau longtemps
-- après PLAYER_LEVEL_UP (jusqu'à la sortie du jeu) ; l'événement de montée fait foi, la relecture ne fait
-- que confirmer.
local function raiseLevel(char, level)
  level = tonumber(level)
  if level and level > (char.level or 0) then char.level = level end
end

local function scan(char)
  local first, surname = ns.UnitNames("player")
  char.name = first or char.name
  if surname then char.surname = surname end
  char.realm = (GetRealmName and GetRealmName()) or char.realm
  local _, classToken = UnitClass("player")
  local _, raceToken = UnitRace("player")
  char.class = classToken or char.class
  char.race = raceToken or char.race
  raiseLevel(char, UnitLevel("player"))
  char.faction = (UnitFactionGroup and UnitFactionGroup("player")) or char.faction
  char.identity_at = ns.now()
end

-- Le temps de jeu arrive par un message système que l'on masque.
local awaiting = false
local function filterPlayed(_, _, msg)
  if awaiting and msg and (TIME_PLAYED_MSG == nil or true) then
    if msg:find("^" .. ((TIME_PLAYED_TOTAL or "Temps total joué") :gsub("%%s", ".*"):gsub("%%d", "%%d+"))) or
       msg:find("^" .. ((TIME_PLAYED_LEVEL or "Temps joué à ce niveau"):gsub("%%s", ".*"):gsub("%%d", "%%d+"))) then
      return true
    end
  end
  return false
end

ns.RegisterCollector({
  name = "identity",
  events = { PLAYER_LEVEL_UP = true, TIME_PLAYED_MSG = true, PLAYER_ENTERING_WORLD = true },
  scanOn = { PLAYER_LEVEL_UP = true, PLAYER_ENTERING_WORLD = true },
  scan = scan,
  onLogin = function(char)
    if ChatFrame_AddMessageEventFilter and RequestTimePlayed then
      ChatFrame_AddMessageEventFilter("CHAT_MSG_SYSTEM", filterPlayed)
      awaiting = true
      ns.Risky("RequestTimePlayed", RequestTimePlayed)
    end
  end,
  onEvent = function(char, event, ...)
    if event == "PLAYER_LEVEL_UP" then
      local level = ...
      raiseLevel(char, level)
      ns.Journal.Event(char, "level", { level = level })
    elseif event == "TIME_PLAYED_MSG" then
      local total = ...
      awaiting = false
      if type(total) == "number" then char.played = total end
    end
  end,
  status = function(char)
    return char.identity_at and string.format(ns.L.UP_TO_DATE, ns.UI.Ago(char.identity_at)) or ns.L.NEVER_READ
  end,
})
