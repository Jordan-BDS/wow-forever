-- Identité : nom complet, royaume, classe, race, niveau, temps de jeu (opt-in), montées de niveau horodatées.
local ADDON, ns = ...

local function splitName(full)
  if not full then return nil, nil end
  local first, rest = full:match("^(%S+)%s+(.+)$")
  if first then return first, rest end
  return full, nil
end

local function scan(char)
  local name = UnitName("player")
  local full = UnitFullName and select(1, UnitFullName("player")) or name
  local first, surname = splitName(full or name)
  char.name = first or char.name
  if surname then char.surname = surname end
  char.realm = (GetRealmName and GetRealmName()) or char.realm
  local _, classToken = UnitClass("player")
  local _, raceToken = UnitRace("player")
  char.class = classToken or char.class
  char.race = raceToken or char.race
  char.level = UnitLevel("player") or char.level
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
      RequestTimePlayed()
    end
  end,
  onEvent = function(char, event, ...)
    if event == "PLAYER_LEVEL_UP" then
      local level = ...
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
