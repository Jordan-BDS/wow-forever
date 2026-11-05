-- PvE : entrées en instance, boss tués (horodatés, avec la part de guildiens du groupe), instances terminées, morts
-- (tueur = la cible hostile au moment de mourir : le journal de combat est interdit aux addons sur Forever).
local ADDON, ns = ...

local inInstance = false

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

--- Qui m'a tué : sans journal de combat (interdit aux addons sur Forever), la cible hostile au moment de la mort.
local function killerName()
  if not (UnitExists and UnitExists("target")) then return nil end
  if UnitCanAttack and not UnitCanAttack("player", "target") then return nil end
  local name = ns.plain(UnitName("target"))
  return type(name) == "string" and name ~= "" and name or nil
end

ns.RegisterCollector({
  name = "pve",
  events = {
    PLAYER_ENTERING_WORLD = true, ENCOUNTER_END = true, PLAYER_DEAD = true,
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
    elseif event == "PLAYER_DEAD" then
      ns.Journal.Increment(char, "deaths")
      local zone = (GetZoneText and GetZoneText()) or ""
      local sub = (GetSubZoneText and GetSubZoneText()) or ""
      local death = ns.Journal.Event(char, "death", { zone = zone, sub = sub, killer = killerName(), level = char.level })
      if ns.OnDeath then ns.Safe("deaths.announce", ns.OnDeath, char, death) end
    end
  end,
  status = function(char)
    local c = char.counters or {}
    return string.format("%d boss · %d donjons · %d morts · %d créatures", c.boss_kills or 0, c.dungeons_done or 0, c.deaths or 0, c.kills or 0)
  end,
})
