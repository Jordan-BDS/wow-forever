-- Journal quotidien (valeur des compteurs en fin de journée, 60 jours) et événements horodatés (500 derniers).
-- Les compteurs sont cumulés et ne sont jamais remis à zéro : le site fait les différences.
local ADDON, ns = ...

local Journal = {}
ns.Journal = Journal

--- Clé de journée selon l'horloge locale du PC (limite acceptée au cahier des charges).
function Journal.DayKey(ts)
  return date("%Y-%m-%d", ts)
end

local function copy(t)
  local out = {}
  for k, v in pairs(t) do
    if type(v) == "table" then out[k] = copy(v) else out[k] = v end
  end
  return out
end
Journal.copy = copy

--- Fige l'instantané du jour courant (appelé à la déconnexion, réécrit jusqu'à minuit).
function Journal.Snapshot(entry, ts)
  local day = Journal.DayKey(ts)
  entry.journal[day] = copy(entry.counters)
  entry.journal_day = day
  Journal.Prune(entry, ts)
end

--- Détecte le passage de minuit en session : fige la journée qui se termine, ouvre la suivante.
--- Renvoie true si la journée a changé.
function Journal.Rollover(entry, ts)
  local today = Journal.DayKey(ts)
  if entry.journal_day == nil then
    entry.journal_day = today
    return false
  end
  if entry.journal_day == today then return false end
  entry.journal[entry.journal_day] = copy(entry.counters)
  entry.journal_day = today
  Journal.Prune(entry, ts)
  return true
end

function Journal.Prune(entry, ts)
  local cutoff = Journal.DayKey(ts - ns.Data.JOURNAL_DAYS * 86400)
  for day in pairs(entry.journal) do
    if day < cutoff then entry.journal[day] = nil end
  end
end

function Journal.Increment(entry, key, amount)
  entry.counters[key] = (entry.counters[key] or 0) + (amount or 1)
  return entry.counters[key]
end

--- Compteur à deux niveaux : counters[group][subkey] += amount.
function Journal.IncrementIn(entry, group, subkey, amount)
  local bucket = entry.counters[group]
  if type(bucket) ~= "table" then
    bucket = {}
    entry.counters[group] = bucket
  end
  subkey = tostring(subkey)
  bucket[subkey] = (bucket[subkey] or 0) + (amount or 1)
  return bucket[subkey]
end

function Journal.Event(entry, kind, data, ts)
  local event = { t = ts or ns.now(), k = kind }
  for key, value in pairs(data or {}) do event[key] = value end
  table.insert(entry.events, event)
  while #entry.events > ns.Data.MAX_EVENTS do table.remove(entry.events, 1) end
  return event
end
