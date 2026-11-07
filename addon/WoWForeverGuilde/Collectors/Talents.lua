-- Talents : rang par talent, repéré par arbre / rangée / colonne (et par sort quand le client ne donne que ça),
-- arbre dominant. Forever tourne sur une base moderne (12.1.5) avec des arbres Classic : l'API exacte n'est pas
-- connue d'avance, on essaie dans l'ordre l'API Classic (GetTalentInfo en valeurs), sa forme récente
-- (C_SpecializationInfo.GetTalentInfo en table, Classic Era 1.15+), puis les traits modernes (C_ClassTalents /
-- C_Traits : rang par identifiant de sort, que le site relie aux talents). Aucune ne répond : « indisponible »,
-- noté une fois par session dans /mf erreurs pour que le GM le voie dans « Tests en jeu ».
local ADDON, ns = ...

local available = nil
local reported = false

--- Fonction globale ou de l'espace C_SpecializationInfo, selon le client.
local function fn(name)
  local f = _G[name]
  if type(f) == "function" then return f end
  f = C_SpecializationInfo and C_SpecializationInfo[name]
  if type(f) == "function" then return f end
  return nil
end

--- Lecture d'un talent : GetTalentInfo renvoie des valeurs (nom, icône, rangée, colonne, rang, rang max) ou,
--- sur les clients récents, une table (name, icon, tier, column, rank, maxRank).
local function talentFields(a, _, c, d, e)
  if type(a) == "table" then
    return ns.plain(a.name), ns.plain(a.tier or a.row), ns.plain(a.column), ns.plain(a.rank) or 0
  end
  return ns.plain(a), ns.plain(c), ns.plain(d), ns.plain(e) or 0
end

--- Nom d'un arbre : Classic Era renvoie (id, nom, …), vanilla (nom, icône, …).
local function tabName(tab)
  if not GetTalentTabInfo then return nil end
  local ok, first, second = pcall(GetTalentTabInfo, tab)
  if not ok then return nil end
  local name = ns.plain(type(first) == "number" and second or first)
  return type(name) == "string" and name or nil
end

--- Arbres Classic : { { name, talents = { { index, tier, column, rank } } } }, ou nil si l'API manque.
local function readTabs()
  local numTabs, numTalents, info = fn("GetNumTalentTabs"), fn("GetNumTalents"), fn("GetTalentInfo")
  if not (numTabs and numTalents and info) then return nil end
  local tabs = {}
  for tab = 1, ns.plain(numTabs()) or 0 do
    local list = {}
    for index = 1, ns.plain(numTalents(tab)) or 0 do
      local ok, a, b, c, d, e = pcall(info, tab, index)
      if ok and a ~= nil then
        local _, tier, column, rank = talentFields(a, b, c, d, e)
        list[#list + 1] = { index = index, tier = tier, column = column, rank = rank }
      end
    end
    tabs[#tabs + 1] = { name = tabName(tab), talents = list }
  end
  return { api = GetTalentInfo and "classic" or "spec", tabs = tabs }
end

--- Traits modernes : rang par sort ({ ["sortId"] = rang }), ou nil si l'API manque ou n'a pas de configuration.
local function readTraits()
  if not (C_ClassTalents and C_ClassTalents.GetActiveConfigID and C_Traits and C_Traits.GetConfigInfo) then
    return nil
  end
  local configID = ns.plain(C_ClassTalents.GetActiveConfigID())
  if type(configID) ~= "number" then return nil end
  local config = C_Traits.GetConfigInfo(configID)
  if type(config) ~= "table" or type(config.treeIDs) ~= "table" then return nil end
  local spells, count = {}, 0
  for _, treeID in ipairs(config.treeIDs) do
    for _, nodeID in ipairs(C_Traits.GetTreeNodes(treeID) or {}) do
      local node = C_Traits.GetNodeInfo(configID, nodeID)
      local rank = node and (ns.plain(node.activeRank) or ns.plain(node.ranksPurchased) or ns.plain(node.currentRank)) or 0
      if type(rank) == "number" and rank > 0 then
        local entryID = (node.activeEntry and node.activeEntry.entryID) or (node.entryIDs and node.entryIDs[1])
        local entry = entryID and C_Traits.GetEntryInfo(configID, entryID)
        local def = entry and entry.definitionID and C_Traits.GetDefinitionInfo(entry.definitionID)
        local spell = def and ns.plain(def.spellID)
        if type(spell) == "number" then
          spells[tostring(spell)] = rank
          count = count + 1
        end
      end
    end
  end
  return { api = "traits", spells = spells, count = count }
end

local function read()
  return readTabs() or readTraits()
end

local function scan(char)
  local result = read()
  if not result then
    available = false
    if not reported then
      reported = true
      ns.Store.LogError("talents.scan", ns.L.TALENTS_NO_API)
    end
    return
  end
  available = true
  local talents = { api = result.api }
  local total, specTab = 0, nil
  if result.tabs then
    -- points : « arbre-index » (ancien format) ; grid : « arbre-rangée-colonne », ce que le site préfère.
    local tabs, points, grid, best, bestPoints = ns.Json.array(), {}, {}, nil, -1
    for tab, t in ipairs(result.tabs) do
      local spent = 0
      for _, talent in ipairs(t.talents) do
        if talent.rank > 0 then
          spent = spent + talent.rank
          points[tab .. "-" .. talent.index] = talent.rank
          if type(talent.tier) == "number" and type(talent.column) == "number" then
            grid[tab .. "-" .. talent.tier .. "-" .. talent.column] = talent.rank
          end
        end
      end
      tabs[#tabs + 1] = spent
      total = total + spent
      if spent > bestPoints then best, bestPoints = tab, spent end
    end
    talents.tabs, talents.points, talents.grid = tabs, points, grid
    specTab = bestPoints > 0 and best or nil
  else
    talents.spells = result.spells
    total = result.count or 0
    specTab = nil -- le site déduit l'arbre dominant des sorts
  end
  -- Aucun point lu alors qu'un build était connu : lecture creuse (connexion, déconnexion, API pas prête), on garde
  -- le dernier build plutôt que de l'effacer sur le site. Une vraie remise à zéro est suivie d'une relecture.
  if total == 0 and char.talents_at then return end
  char.talents = talents
  char.spec_tab = specTab
  char.talents_at = ns.now()
end

--- Résumé lisible « Amélioration 31/20/0 » (arbre dominant, puis points par arbre), "" si indisponible ou sans arbres.
function ns.TalentSummary()
  local result = readTabs()
  if not result then return "" end
  local spent, best, bestPoints, total = {}, nil, 0, 0
  for tab, t in ipairs(result.tabs) do
    local points = 0
    for _, talent in ipairs(t.talents) do points = points + talent.rank end
    spent[#spent + 1] = tostring(points)
    total = total + points
    if points > bestPoints then best, bestPoints = tab, points end
  end
  if total == 0 then return "" end
  local name = best and result.tabs[best].name
  return (name and (name .. " ") or "") .. table.concat(spent, "/")
end

--- Pour /mf api : quelle lecture des talents répond sur ce client.
function ns.TalentApi()
  local result = read()
  return result and result.api or nil
end

ns.RegisterCollector({
  name = "talents",
  events = { PLAYER_TALENT_UPDATE = true, CHARACTER_POINTS_CHANGED = true, SPELLS_CHANGED = true, TRAIT_CONFIG_UPDATED = true },
  scanOn = { PLAYER_TALENT_UPDATE = true, CHARACTER_POINTS_CHANGED = true, TRAIT_CONFIG_UPDATED = true },
  scan = scan,
  status = function(char)
    if available == false then return ns.L.NOT_AVAILABLE end
    return char.talents_at and string.format(ns.L.UP_TO_DATE, ns.UI.Ago(char.talents_at)) or ns.L.NEVER_READ
  end,
})
