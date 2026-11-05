-- Créatures tuées. Forever interdit le journal de combat aux addons (ADDON_ACTION_FORBIDDEN) : on lit le message
-- d'expérience « Sanglier meurt, vous gagnez 45 points d'expérience. », donc toute créature qui rapporte de
-- l'expérience, en solo comme en groupe. Au niveau maximum il n'y a plus de message : les kills ne sont plus comptés.
-- Le compteur cumulé `kills` et le nombre par créature (`counters.mobs`, clé = nom, faute d'identifiant) suivent
-- les périodes dans le journal quotidien ; le détail (premier et dernier kill) vit dans `char.mobs`, hors journal.
local ADDON, ns = ...

--- Motif Lua construit depuis la chaîne du jeu « %s meurt, vous gagnez %d points d'expérience. » : on ne garde que
--- le début, jusqu'au nom et au verbe, pour couvrir aussi les variantes de groupe (« (+%d bonus de groupe) »).
local pattern
local function xpPattern()
  if pattern then return pattern end
  local template = COMBATLOG_XPGAIN_FIRSTPERSON or "%s meurt, vous gagnez %d points d'expérience."
  local head = template:match("^(.-)%%d") or template -- jusqu'au nombre de points
  head = head:gsub("[%^%$%(%)%.%[%]%*%+%-%?]", "%%%0") -- caractères magiques
  head = head:gsub("%%s", "(.-)", 1) -- %s → nom de la créature
  pattern = "^" .. head
  return pattern
end
ns.XpPattern = xpPattern

--- Nom de la créature tuée d'après un message d'expérience, nil sinon.
local function killedName(msg)
  if type(msg) ~= "string" then return nil end
  local name = msg:match(xpPattern())
  if name and name ~= "" then return name end
  return nil
end
ns.KilledName = killedName

--- Garde au plus MAX_MOBS créatures distinctes : on oublie d'abord les moins tuées, puis les plus anciennes.
local function capMobs(mobs, counts)
  local keys = {}
  for key in pairs(mobs) do keys[#keys + 1] = key end
  if #keys <= ns.Data.MAX_MOBS then return end
  table.sort(keys, function(a, b)
    local ma, mb = mobs[a], mobs[b]
    if ma.n ~= mb.n then return ma.n < mb.n end
    return (ma.last or 0) < (mb.last or 0)
  end)
  for i = 1, #keys - ns.Data.MAX_MOBS do
    mobs[keys[i]] = nil
    if counts then counts[keys[i]] = nil end
  end
end

local function recordKill(char, name, t)
  ns.Journal.Increment(char, "kills")
  local mobs = char.mobs
  if type(mobs) ~= "table" then mobs = {}; char.mobs = mobs end
  local record = mobs[name]
  if not record then
    record = { n = 0, first = t, name = name }
    mobs[name] = record
    capMobs(mobs, char.counters.mobs)
    if mobs[name] ~= record then return end -- évincé immédiatement : la table est pleine de créatures plus tuées
  end
  record.n = record.n + 1
  record.last = t
  ns.Journal.IncrementIn(char, "mobs", name)
end

ns.RegisterCollector({
  name = "kills",
  events = { CHAT_MSG_COMBAT_XP_GAIN = true },
  onEvent = function(char, event, msg)
    local name = killedName(ns.plain(msg))
    if name then recordKill(char, name, ns.now()) end
  end,
  status = function(char)
    local n, distinct = (char.counters and char.counters.kills) or 0, 0
    for _ in pairs(char.mobs or {}) do distinct = distinct + 1 end
    return string.format("%d créatures tuées · %d espèces", n, distinct)
  end,
})
