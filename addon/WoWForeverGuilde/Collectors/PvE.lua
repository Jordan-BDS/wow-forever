-- PvE : entrées en instance, boss tués (horodatés, avec la part de guildiens du groupe), instances terminées, morts.
-- La dernière source de dégâts est mémorisée pour l'annonce de mort.
local ADDON, ns = ...

local inInstance = false
ns.lastDamage = nil

local DAMAGE_EVENTS = {
  SWING_DAMAGE = true, RANGE_DAMAGE = true, SPELL_DAMAGE = true, SPELL_PERIODIC_DAMAGE = true,
  SPELL_BUILDING_DAMAGE = true, ENVIRONMENTAL_DAMAGE = true, DAMAGE_SPLIT = true, DAMAGE_SHIELD = true,
}

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

local function onCombatLog(char)
  if not CombatLogGetCurrentEventInfo then return end
  local _, subevent, _, _, sourceName, _, _, destGUID = CombatLogGetCurrentEventInfo()
  subevent = ns.plain(subevent)
  if not subevent or not DAMAGE_EVENTS[subevent] then return end
  if ns.plain(destGUID) ~= (char and char.guid) then return end
  if subevent == "ENVIRONMENTAL_DAMAGE" then
    local envType = select(12, CombatLogGetCurrentEventInfo())
    ns.lastDamage = { env = ns.plain(envType), t = ns.now() }
  else
    ns.lastDamage = { source = ns.plain(sourceName), t = ns.now() }
  end
end

ns.RegisterCollector({
  name = "pve",
  events = {
    PLAYER_ENTERING_WORLD = true, ENCOUNTER_END = true, PLAYER_DEAD = true, COMBAT_LOG_EVENT_UNFILTERED = true,
  },
  onEvent = function(char, event, ...)
    if event == "COMBAT_LOG_EVENT_UNFILTERED" then
      onCombatLog(char)
    elseif event == "PLAYER_ENTERING_WORLD" then
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
      local last = ns.lastDamage
      local killer, env = nil, nil
      if last and ns.now() - (last.t or 0) <= 10 then killer, env = last.source, last.env end
      local death = ns.Journal.Event(char, "death", { zone = zone, sub = sub, killer = killer, env = env, level = char.level })
      if ns.OnDeath then ns.Safe("deaths.announce", ns.OnDeath, char, death) end
    end
  end,
  status = function(char)
    local c = char.counters or {}
    return string.format("%d boss · %d donjons · %d morts", c.boss_kills or 0, c.dungeons_done or 0, c.deaths or 0)
  end,
})
