-- Wanted : têtes mises à prix. Un joueur adverse qui tue un membre (mort annoncée par message « D » avec « tueur
-- joueur ») prend un point de prime, jamais remis à zéro (décision du 9 novembre 2026). Le tableau vit au niveau du
-- compte (`db.wanted`, clé = nom en minuscules) : il se remplit avec les morts reçues pendant qu'on est connecté, la
-- sienne comprise ; l'écho de son propre message est reconnu comme un doublon (même victime, même heure). La
-- dernière position connue d'un ennemi est celle de sa victime au moment de mourir : « là où il a frappé ».
-- Lot 1 : tableau, avis de décès avec prime, tête de mort sur la carte 5 min, fenêtre /mf wanted. Les kills par la
-- guilde (`kills`) et la poignée de main entre clients viendront au lot 2.
local ADDON, ns = ...

local Wanted = {}
ns.Wanted = Wanted
local L = ns.L

--- Clé d'un ennemi : son nom affiché en minuscules, espaces de bord retirés (pas de royaume sur Forever).
function Wanted.Key(name)
  return (tostring(name or ""):gsub("^%s+", ""):gsub("%s+$", "")):lower()
end

local function table_()
  local db = ns.db
  if not db then return nil end
  db.wanted = db.wanted or {}
  return db.wanted
end

function Wanted.Get(name)
  local t = table_()
  return t and t[Wanted.Key(name)] or nil
end

--- Garde au plus WANTED_MAX ennemis : les primes les plus faibles sautent d'abord, puis les plus anciennes.
local function cap(t)
  local keys = {}
  for key in pairs(t) do keys[#keys + 1] = key end
  if #keys <= ns.Data.WANTED_MAX then return end
  table.sort(keys, function(a, b)
    local ea, eb = t[a], t[b]
    if (ea.points or 0) ~= (eb.points or 0) then return (ea.points or 0) < (eb.points or 0) end
    return ((ea.last and ea.last.t) or 0) < ((eb.last and eb.last.t) or 0)
  end)
  for i = 1, #keys - ns.Data.WANTED_MAX do
    if ns.MapUI then ns.MapUI.RemoveWanted(keys[i]) end
    t[keys[i]] = nil
  end
end

--- Une mort reçue (ligne « D » décodée). Renvoie l'entrée de l'ennemi et vrai si un point a été ajouté ; nil si le
--- tueur n'est pas un joueur nommé. Doublon (même victime, même heure) : l'entrée, et faux.
function Wanted.RecordDeath(info)
  if type(info) ~= "table" or not info.player then return nil end
  local killer = tostring(info.killer or "")
  if killer == "" or killer == L.KILLER_UNKNOWN then return nil end
  local t = table_()
  if not t then return nil end
  local key = Wanted.Key(killer)
  if key == "" then return nil end
  local at = tonumber(info.t) or ns.now()
  local entry = t[key]
  if not entry then
    entry = { name = killer, points = 0, kills = 0, first = at, victims = {} }
    t[key] = entry
    cap(t)
    if t[key] ~= entry then return nil end -- évincé aussitôt : le tableau est plein d'ennemis plus recherchés
  end
  entry.victims = entry.victims or {}
  for _, victim in ipairs(entry.victims) do
    if victim.guid == info.guid and victim.t == at then return entry, false end
  end
  entry.points = (entry.points or 0) + 1
  if info.kclass and info.kclass ~= "" then entry.class = info.kclass end
  table.insert(entry.victims, { guid = info.guid, name = info.name, class = info.class, t = at })
  while #entry.victims > ns.Data.WANTED_VICTIMS do table.remove(entry.victims, 1) end
  entry.last = {
    t = at, map = info.map, x = info.x, y = info.y, zone = info.zone or "", sub = info.sub or "",
    victim = info.name, victimClass = info.class,
  }
  if ns.MapUI then ns.MapUI.UpdateWanted(entry) end
  if ns.WantedUI then ns.WantedUI.Refresh() end
  return entry, true
end

--- Ligne de chat quand un recherché frappe (le popup, s'il est affiché, porte déjà la prime).
function Wanted.Announce(entry, info)
  local place = info.zone ~= "" and info.zone or (info.sub ~= "" and info.sub or L.WHERE_UNKNOWN)
  ns.Print(L.WANTED_CHAT, ns.ClassColored(entry.name, entry.class), ns.ClassColored(info.name, info.class), place, entry.points or 0)
end

--- La dernière position est-elle encore à montrer (moins de WANTED_TTL s) ?
function Wanted.Fresh(entry, now)
  local last = entry.last
  return last ~= nil and last.map ~= nil and last.x ~= nil and last.y ~= nil and (last.t or 0) >= (now or ns.now()) - ns.Data.WANTED_TTL
end

--- Zone et sous-zone de la dernière victime.
function Wanted.Where(entry)
  local last = entry.last
  if not last then return "" end
  local text = last.zone or ""
  if last.sub and last.sub ~= "" and last.sub ~= last.zone then
    text = text ~= "" and (text .. " · " .. last.sub) or last.sub
  end
  return text
end

--- Ennemis triés : prime décroissante, puis dernière victime la plus récente.
function Wanted.Sorted()
  local list = {}
  for _, entry in pairs(table_() or {}) do list[#list + 1] = entry end
  table.sort(list, function(a, b)
    if (a.points or 0) ~= (b.points or 0) then return (a.points or 0) > (b.points or 0) end
    return ((a.last and a.last.t) or 0) > ((b.last and b.last.t) or 0)
  end)
  return list
end

--- Toutes les 10 s : la tête de mort pâlit puis disparaît au bout de WANTED_TTL s.
function Wanted.Tick()
  if not ns.MapUI then return end
  local now = ns.now()
  for key, entry in pairs(table_() or {}) do
    if Wanted.Fresh(entry, now) then ns.MapUI.UpdateWanted(entry) else ns.MapUI.RemoveWanted(key) end
  end
end

--- Case « Alertes Wanted » : décoché, les têtes de mort quittent la carte ; coché, celles encore fraîches reviennent.
function Wanted.SetAlerts(on)
  ns.db.settings.wantedAlerts = on and true or false
  Wanted.Tick()
end

ns.RegisterCollector({
  name = "wanted",
  events = {},
  onLogin = function()
    C_Timer.After(5, function() ns.Safe("wanted.tick", Wanted.Tick) end)
    C_Timer.NewTicker(ns.Data.POSITION_TICK, function() ns.Safe("wanted.tick", Wanted.Tick) end)
  end,
})
