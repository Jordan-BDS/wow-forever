-- Créatures tuées : un kill est compté quand une créature que moi (ou mon familier, mes totems…) ai frappée dans
-- les KILL_WINDOW dernières secondes meurt (même logique que le crédit de quête du jeu : pas besoin du coup fatal).
-- Un compteur cumulé `kills` suit les périodes dans le journal ; le détail par créature (identifiant de PNJ, nom,
-- nombre, dernier kill) vit dans `char.mobs`, hors du journal quotidien pour ne pas gonfler le fichier.
local ADDON, ns = ...

local DAMAGE_EVENTS = {
  SWING_DAMAGE = true, RANGE_DAMAGE = true, SPELL_DAMAGE = true, SPELL_PERIODIC_DAMAGE = true,
  SPELL_BUILDING_DAMAGE = true, DAMAGE_SPLIT = true, DAMAGE_SHIELD = true,
}
local AFFILIATION_MINE, CONTROL_PLAYER = 0x1, 0x100

local touched = {} -- GUID de créature → { t = dernier coup, name = nom }
local touchedCount = 0
local lastPrune = 0

local function hasFlag(flags, flag)
  return type(flags) == "number" and math.floor(flags / flag) % 2 == 1
end

--- Identifiant de PNJ d'un GUID « Creature-0-serveur-instance-zone-NPCID-spawn » (ou Vehicle-…).
local function npcId(guid)
  if type(guid) ~= "string" then return nil end
  local id = guid:match("^Creature%-%d+%-%d+%-%d+%-%d+%-(%d+)%-") or guid:match("^Vehicle%-%d+%-%d+%-%d+%-%d+%-(%d+)%-")
  return id and tonumber(id) or nil
end
ns.NpcId = npcId

--- La source du coup, c'est moi ou une de mes unités (familier, totem, gardien).
local function isMine(char, sourceGUID, sourceFlags)
  if sourceGUID ~= nil and sourceGUID == char.guid then return true end
  return hasFlag(sourceFlags, AFFILIATION_MINE)
end

local function prune(t)
  if t - lastPrune < ns.Data.KILL_WINDOW then return end
  lastPrune = t
  for guid, hit in pairs(touched) do
    if t - hit.t > ns.Data.KILL_WINDOW then
      touched[guid] = nil
      touchedCount = touchedCount - 1
    end
  end
end

--- Garde au plus MAX_MOBS créatures distinctes : on oublie d'abord les moins tuées, puis les plus anciennes.
local function capMobs(mobs)
  local keys = {}
  for key in pairs(mobs) do keys[#keys + 1] = key end
  if #keys <= ns.Data.MAX_MOBS then return end
  table.sort(keys, function(a, b)
    local ma, mb = mobs[a], mobs[b]
    if ma.n ~= mb.n then return ma.n < mb.n end
    return (ma.last or 0) < (mb.last or 0)
  end)
  for i = 1, #keys - ns.Data.MAX_MOBS do mobs[keys[i]] = nil end
end

local function recordKill(char, id, name, t)
  ns.Journal.Increment(char, "kills")
  local mobs = char.mobs
  if type(mobs) ~= "table" then mobs = {}; char.mobs = mobs end
  local key = tostring(id)
  local record = mobs[key]
  if not record then
    record = { n = 0, first = t }
    mobs[key] = record
    capMobs(mobs)
    if mobs[key] ~= record then return end -- évincé immédiatement : la table est pleine de créatures plus tuées
  end
  record.n = record.n + 1
  record.last = t
  if type(name) == "string" and name ~= "" then record.name = name end
end

local function onCombatLog(char)
  if not CombatLogGetCurrentEventInfo or not char or not char.guid then return end
  local _, subevent, _, sourceGUID, _, sourceFlags, _, destGUID, destName, destFlags = CombatLogGetCurrentEventInfo()
  subevent = ns.plain(subevent)
  if not subevent then return end
  destGUID = ns.plain(destGUID)
  local id = npcId(destGUID)
  if not id then return end -- joueurs, familiers, objets : pas des créatures
  local t = ns.now()
  if DAMAGE_EVENTS[subevent] then
    if hasFlag(ns.plain(destFlags), CONTROL_PLAYER) then return end -- totems, gardiens d'un joueur
    if not isMine(char, ns.plain(sourceGUID), ns.plain(sourceFlags)) then return end
    local hit = touched[destGUID]
    if hit then
      hit.t = t
    else
      touched[destGUID] = { t = t, name = ns.plain(destName) }
      touchedCount = touchedCount + 1
    end
    if touchedCount > 50 then prune(t) end
  elseif subevent == "PARTY_KILL" then
    -- Coup fatal porté par moi : compté tout de suite, et UNIT_DIED juste après ne recomptera pas.
    if not isMine(char, ns.plain(sourceGUID), ns.plain(sourceFlags)) then return end
    if hasFlag(ns.plain(destFlags), CONTROL_PLAYER) then return end
    local hit = touched[destGUID]
    if hit then touched[destGUID] = nil; touchedCount = touchedCount - 1 end
    recordKill(char, id, ns.plain(destName) or (hit and hit.name), t)
  elseif subevent == "UNIT_DIED" then
    local hit = touched[destGUID]
    if not hit then return end
    touched[destGUID] = nil
    touchedCount = touchedCount - 1
    if t - hit.t > ns.Data.KILL_WINDOW then return end
    recordKill(char, id, ns.plain(destName) or hit.name, t)
  end
end

ns.RegisterCollector({
  name = "kills",
  events = { COMBAT_LOG_EVENT_UNFILTERED = true, PLAYER_ENTERING_WORLD = true },
  onEvent = function(char, event)
    if event == "COMBAT_LOG_EVENT_UNFILTERED" then
      onCombatLog(char)
    else
      touched, touchedCount = {}, 0 -- changement de monde : les cibles en cours ne mourront plus sous nos yeux
    end
  end,
  status = function(char)
    local n, distinct = (char.counters and char.counters.kills) or 0, 0
    for _ in pairs(char.mobs or {}) do distinct = distinct + 1 end
    return string.format("%d créatures tuées · %d espèces", n, distinct)
  end,
})
