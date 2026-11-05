-- Métiers : compétence dès la connexion ; recettes connues seulement quand la fenêtre du métier est ouverte.
-- Sur une base moderne, un métier a une ligne de compétence « mère » (Alchimie, 171) et une ligne par extension
-- (« Alchimie Classic ») : on remonte toujours à la mère, c'est elle que le site connaît ; la compétence vient de
-- la ligne d'extension quand la mère n'en a pas.
local ADDON, ns = ...

local available = nil
local reported = false

local function entryFor(char, skillLine)
  char.professions = char.professions or {}
  local key = tostring(skillLine)
  char.professions[key] = char.professions[key] or { id = skillLine }
  return char.professions[key]
end

--- Ligne mère d'une ligne de compétence (elle-même si le client ne connaît pas la hiérarchie), et la fiche de la
--- ligne lue (compétence propre à cette ligne) quand le client la donne.
local function parentLine(skillLine)
  local api = C_TradeSkillUI and C_TradeSkillUI.GetProfessionInfoBySkillLineID
  if api then
    local ok, info = pcall(api, skillLine)
    if ok and type(info) == "table" then
      local parent = ns.plain(info.parentProfessionID)
      return (type(parent) == "number" and parent > 0) and parent or skillLine, info
    end
  end
  return skillLine, nil
end

--- Une valeur de compétence n'écrase l'ancienne que si elle dit quelque chose (ni nil, ni 0, ni secrète).
local function positive(value, fallback)
  value = ns.plain(value)
  if type(value) == "number" and value > 0 then return value end
  return fallback
end

--- Métiers connus (sans recettes) : GetProfessions (moderne) → GetProfessionInfo.
local function scanKnown(char)
  if not (GetProfessions and GetProfessionInfo) then
    available = false
    if not reported then
      reported = true
      ns.Store.LogError("professions.scan", ns.L.PROFESSIONS_NO_API)
    end
    return
  end
  available = true
  local seen = {}
  -- GetProfessions renvoie 6 emplacements (métier 1, métier 2, archéologie, pêche, cuisine, secourisme) avec des
  -- trous : ipairs s'arrêterait au premier nil, on parcourt donc par select en ignorant les emplacements vides.
  local function scanSlots(...)
    for i = 1, select("#", ...) do
      local index = select(i, ...)
      if type(index) == "number" then
        local name, _, skill, max, _, _, skillLine = GetProfessionInfo(index)
        skillLine = ns.plain(skillLine)
        if type(skillLine) == "number" then
          local parent, lineInfo = parentLine(skillLine)
          local prof = entryFor(char, parent)
          prof.name = ns.plain(name) or prof.name
          prof.line = skillLine -- ligne telle que lue, pour comprendre un métier que le site ne reconnaît pas
          -- La mère peut dire 0 sur une base moderne : la compétence est alors celle de la ligne lue.
          prof.skill = positive(skill, positive(lineInfo and lineInfo.skillLevel, prof.skill))
          prof.max = positive(max, positive(lineInfo and lineInfo.maxSkillLevel, prof.max))
          seen[tostring(parent)] = true
        end
      end
    end
  end
  scanSlots(GetProfessions())
  -- Un métier abandonné disparaît.
  for key in pairs(char.professions or {}) do
    if not seen[key] then char.professions[key] = nil end
  end
  char.professions_at = ns.now()
end

--- Fenêtre d'un métier ouverte : liste des recettes apprises.
local function scanOpen(char)
  if not C_TradeSkillUI then return end
  if C_TradeSkillUI.IsTradeSkillLinked and C_TradeSkillUI.IsTradeSkillLinked() then return end -- métier d'un autre
  local base = C_TradeSkillUI.GetBaseProfessionInfo and C_TradeSkillUI.GetBaseProfessionInfo()
  local child = C_TradeSkillUI.GetChildProfessionInfo and C_TradeSkillUI.GetChildProfessionInfo()
  if type(base) ~= "table" then base = nil end
  if type(child) ~= "table" then child = nil end
  local info = base or child
  if not info and C_TradeSkillUI.GetTradeSkillLine then
    local id, name, skill, max = C_TradeSkillUI.GetTradeSkillLine()
    info = id and { professionID = id, professionName = name, skillLevel = skill, maxSkillLevel = max } or nil
  end
  local id = info and ns.plain(info.professionID)
  if type(id) ~= "number" or id <= 0 then return end
  local parent = positive(info.parentProfessionID, nil) or parentLine(id)
  local prof = entryFor(char, parent)
  prof.name = ns.plain(info.professionName) or prof.name
  -- La ligne d'extension porte la compétence ; la mère parfois 0 sur une base moderne.
  prof.skill = positive(child and child.skillLevel, positive(info.skillLevel, prof.skill))
  prof.max = positive(child and child.maxSkillLevel, positive(info.maxSkillLevel, prof.max))
  local recipes = {}
  for _, recipeId in ipairs(C_TradeSkillUI.GetAllRecipeIDs() or {}) do
    local r = C_TradeSkillUI.GetRecipeInfo(recipeId)
    if r and r.learned then recipes[#recipes + 1] = recipeId end
  end
  table.sort(recipes)
  prof.recipes = recipes
  prof.read_at = ns.now()
  ns.knownRecipes = ns.knownRecipes or {}
  for _, rid in ipairs(recipes) do ns.knownRecipes[rid] = true end
end

local function neverRead(char)
  local missing = {}
  for _, prof in pairs(char.professions or {}) do
    if not prof.recipes then missing[#missing + 1] = prof.name or tostring(prof.id) end
  end
  table.sort(missing)
  return missing
end
ns.ProfessionsNeverRead = neverRead

ns.RegisterCollector({
  name = "professions",
  events = { SKILL_LINES_CHANGED = true, TRADE_SKILL_SHOW = true, TRADE_SKILL_LIST_UPDATE = true },
  scanOn = { SKILL_LINES_CHANGED = true },
  scan = scanKnown,
  onLogin = function(char)
    -- Reconstitue l'ensemble des recettes connues pour le comptage des fabrications.
    ns.knownRecipes = {}
    for _, prof in pairs(char.professions or {}) do
      for _, id in ipairs(prof.recipes or {}) do ns.knownRecipes[id] = true end
    end
    local missing = neverRead(char)
    if #missing > 0 then
      local last = char.profession_reminder_at or 0
      if ns.now() - last > 7 * 86400 then
        char.profession_reminder_at = ns.now()
        for _, name in ipairs(missing) do ns.Print(ns.L.PROFESSION_NEVER_READ, name) end
      end
    end
  end,
  onEvent = function(char, event)
    if event == "TRADE_SKILL_SHOW" or event == "TRADE_SKILL_LIST_UPDATE" then
      ns.Debounce("professions:open", 1, function() ns.Safe("professions.open", scanOpen, char) end)
    end
  end,
  status = function(char)
    if available == false then return ns.L.NOT_AVAILABLE end
    local lines = {}
    for _, prof in pairs(char.professions or {}) do
      local label = (prof.name or tostring(prof.id)) .. " " .. tostring(prof.skill or "?")
      if prof.recipes then
        lines[#lines + 1] = string.format(ns.L.UP_TO_DATE, label .. " · " .. ns.UI.Ago(prof.read_at))
      else
        lines[#lines + 1] = "|cffffb84a" .. label .. " : jamais lu, ouvre la fenêtre du métier|r"
      end
    end
    table.sort(lines)
    return #lines > 0 and table.concat(lines, "\n") or ns.L.NEVER_READ
  end,
})
