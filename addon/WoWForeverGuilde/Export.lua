-- Code d'export : WFG1:<adler32 du JSON, 8 hex>:<base64 du JSON compressé en DEFLATE brut>.
-- Exactement le format décodé par le site (backend/apps/gamesync/format.py).
local ADDON, ns = ...

local Export = {}
ns.Export = Export

Export.FORMAT_VERSION = 1

local function deflate()
  return (LibStub and LibStub:GetLibrary("LibDeflate", true)) or LibDeflate
end

local function professionList(entry)
  local list = ns.Json.array()
  for _, prof in pairs(entry.professions or {}) do
    local item = { id = prof.id, skill = prof.skill, max = prof.max, spec = prof.spec }
    if prof.recipes then
      local recipes = ns.Json.array()
      for _, id in ipairs(prof.recipes) do recipes[#recipes + 1] = id end
      item.recipes = recipes
      item.read_at = prof.read_at
    end
    list[#list + 1] = item
  end
  table.sort(list, function(a, b) return (a.id or 0) < (b.id or 0) end)
  return list
end

local function arrayOf(t)
  local out = ns.Json.array()
  for _, v in ipairs(t or {}) do out[#out + 1] = v end
  return out
end

--- Représentation d'un personnage telle qu'attendue par le site.
function Export.Character(entry, settings)
  local c = {
    guid = entry.guid,
    name = entry.name,
    surname = entry.surname,
    realm = entry.realm,
    class = entry.class,
    race = entry.race,
    level = entry.level,
    spec_tab = entry.spec_tab,
    exported_at = entry.updated_at,
    counting_since = entry.counting_since,
    gear = entry.gear,
    talents = entry.talents,
    professions = professionList(entry),
    reputations = entry.reputations,
    attunements = entry.attunements,
    lockouts = arrayOf(entry.lockouts),
    pvp = entry.pvp,
    counters = entry.counters,
    journal = entry.journal,
    events = arrayOf(entry.events),
    previous_guids = arrayOf(entry.previous_guids),
  }
  if settings and settings.sharePlaytime then c.played = entry.played end
  return c
end

function Export.BuildPayload(db, ts)
  local characters = ns.Json.array()
  local guids = {}
  for guid, entry in pairs(db.characters) do
    if entry.name and not db.settings.excluded[guid] then guids[#guids + 1] = guid end
  end
  table.sort(guids)
  for _, guid in ipairs(guids) do
    characters[#characters + 1] = Export.Character(db.characters[guid], db.settings)
  end
  return {
    v = Export.FORMAT_VERSION,
    addon = ns.VERSION,
    install = db.installId,
    exported_at = ts or ns.now(),
    characters = characters,
    errors = arrayOf(db.errors),
  }
end

local function hex32(n)
  return string.format("%04x%04x", math.floor(n / 65536), n % 65536)
end

function Export.Encode(payload)
  local lib = deflate()
  local json = ns.Json.encode(payload)
  local compressed = lib:CompressDeflate(json, { level = 7 })
  return string.format("WFG%d:%s:%s", Export.FORMAT_VERSION, hex32(lib:Adler32(json)), ns.Base64.encode(compressed))
end

--- Construit le code depuis la base, le mémorise (lu par le compagnon dans SavedVariables) et le renvoie.
function Export.Build(ts)
  local db = ns.db
  local code = Export.Encode(Export.BuildPayload(db, ts))
  db.export = code
  db.export_at = ts or ns.now()
  return code
end

--- Noms des personnages présents dans le code, pour la fenêtre d'export.
function Export.Describe(db)
  local included, excluded = {}, {}
  for guid, entry in pairs(db.characters) do
    if entry.name then
      if db.settings.excluded[guid] then excluded[#excluded + 1] = entry.name else included[#included + 1] = entry.name end
    end
  end
  table.sort(included)
  table.sort(excluded)
  return included, excluded
end
