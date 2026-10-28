-- Base sauvegardée (WoWForeverGuildeDB, niveau compte) : schéma, migrations, entrée par personnage, erreurs bornées.
local ADDON, ns = ...

local Store = {}
ns.Store = Store

Store.DB_VERSION = 1

local function now()
  return (GetServerTime and GetServerTime()) or time()
end
ns.now = now

local function newInstallId()
  local chars = "abcdefghijklmnopqrstuvwxyz0123456789"
  local out = {}
  for i = 1, 16 do
    local k = math.random(1, #chars)
    out[i] = chars:sub(k, k)
  end
  return table.concat(out)
end

function Store.Init()
  local db = WoWForeverGuildeDB
  if type(db) ~= "table" then
    db = {}
    WoWForeverGuildeDB = db
  end
  db.version = db.version or Store.DB_VERSION
  db.installId = db.installId or newInstallId()
  db.characters = db.characters or {}
  db.errors = db.errors or {}
  db.settings = db.settings or {}
  local s = db.settings
  if s.sharePlaytime == nil then s.sharePlaytime = false end
  if s.announceDeaths == nil then s.announceDeaths = true end
  if s.showDeaths == nil then s.showDeaths = true end
  if s.soundDeaths == nil then s.soundDeaths = true end
  if s.reloadReminder == nil then s.reloadReminder = true end
  s.excluded = s.excluded or {}
  -- Migrations futures : if db.version < 2 then ... end
  db.version = Store.DB_VERSION
  ns.db = db
  return db
end

--- Entrée d'un personnage, créée au besoin.
function Store.Character(guid)
  local db = ns.db
  local entry = db.characters[guid]
  if not entry then
    local t = now()
    entry = {
      guid = guid, created_at = t, counting_since = t, updated_at = t,
      counters = {}, journal = {}, events = {}, previous_guids = {},
      professions = {}, gear = {}, reputations = {}, attunements = {}, lockouts = {}, pvp = {}, talents = {},
    }
    db.characters[guid] = entry
  end
  entry.counters = entry.counters or {}
  entry.journal = entry.journal or {}
  entry.events = entry.events or {}
  entry.previous_guids = entry.previous_guids or {}
  return entry
end

--- Candidat à un transfert / renommage : même classe, même race, niveau inférieur ou égal, GUID différent.
function Store.FindTransferCandidate(guid, class, race, level)
  local best
  for otherGuid, entry in pairs(ns.db.characters) do
    if otherGuid ~= guid and entry.class == class and entry.race == race and (entry.level or 0) <= level then
      if not best or (entry.updated_at or 0) > (best.updated_at or 0) then best = entry end
    end
  end
  return best
end

--- Fusionne l'ancienne entrée dans la nouvelle (compteurs, journal, événements) et garde l'ancien GUID.
function Store.Merge(newEntry, oldEntry)
  for key, value in pairs(oldEntry.counters or {}) do
    if newEntry.counters[key] == nil then newEntry.counters[key] = value end
  end
  for day, snapshot in pairs(oldEntry.journal or {}) do
    if newEntry.journal[day] == nil then newEntry.journal[day] = snapshot end
  end
  for _, event in ipairs(oldEntry.events or {}) do table.insert(newEntry.events, event) end
  table.sort(newEntry.events, function(a, b) return (a.t or 0) < (b.t or 0) end)
  table.insert(newEntry.previous_guids, oldEntry.guid)
  for _, previous in ipairs(oldEntry.previous_guids or {}) do table.insert(newEntry.previous_guids, previous) end
  newEntry.counting_since = math.min(newEntry.counting_since or now(), oldEntry.counting_since or now())
  ns.db.characters[oldEntry.guid] = nil
end

function Store.LogError(where, err)
  local db = ns.db
  if not db then return end
  table.insert(db.errors, { t = now(), where = where, error = tostring(err), addon = ns.VERSION })
  while #db.errors > ns.Data.MAX_ERRORS do table.remove(db.errors, 1) end
end

function Store.IsExcluded(guid)
  return ns.db and ns.db.settings.excluded[guid] == true
end
