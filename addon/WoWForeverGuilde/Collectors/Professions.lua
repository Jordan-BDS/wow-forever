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
  -- Lecture vide (connexion, déconnexion, API pas prête) : on ne touche à rien, sinon les métiers et toutes leurs
  -- recettes partiraient au site comme abandonnés.
  if next(seen) == nil then return end
  -- Un métier abandonné disparaît.
  for key in pairs(char.professions or {}) do
    if not seen[key] then char.professions[key] = nil end
  end
  char.professions_at = ns.now()
end

--- Recettes apprises de la fenêtre ouverte, par l'API moderne (C_TradeSkillUI : identifiants de recette = sorts).
--- nil si l'API n'existe pas.
local function modernRecipes()
  if not (C_TradeSkillUI and C_TradeSkillUI.GetAllRecipeIDs and C_TradeSkillUI.GetRecipeInfo) then return nil end
  local recipes = {}
  for _, recipeId in ipairs(C_TradeSkillUI.GetAllRecipeIDs() or {}) do
    recipeId = ns.plain(recipeId)
    local r = recipeId and C_TradeSkillUI.GetRecipeInfo(recipeId)
    if type(r) == "table" and ns.plain(r.learned) then recipes[#recipes + 1] = recipeId end
  end
  return recipes, "C_TradeSkillUI"
end

--- Recettes de la fenêtre ouverte par l'API Classic : la liste mêle en-têtes et recettes, et le sort de chaque
--- recette est dans son lien « |Henchant:ID| ». Fenêtre de métier (cuisine, forge…) ou d'enchantement (Craft).
local function classicRecipes()
  local num, info, link
  if GetNumTradeSkills and GetTradeSkillInfo and GetTradeSkillRecipeLink then
    num, info, link = GetNumTradeSkills, GetTradeSkillInfo, GetTradeSkillRecipeLink
  elseif GetNumCrafts and GetCraftInfo and GetCraftRecipeLink then
    num, info, link = GetNumCrafts, GetCraftInfo, GetCraftRecipeLink
  else
    return nil
  end
  local recipes = {}
  for i = 1, (ns.plain(num()) or 0) do
    local _, kind = info(i)
    if ns.plain(kind) ~= "header" then
      local spell = tostring(ns.plain(link(i)) or ""):match("|Henchant:(%d+)")
      if spell then recipes[#recipes + 1] = tonumber(spell) end
    end
  end
  return recipes, link == GetCraftRecipeLink and "Craft" or "TradeSkill"
end

--- Ligne de la fenêtre ouverte : { professionID, professionName, skillLevel, maxSkillLevel, parentProfessionID }
--- et la fiche d'extension, par l'API moderne puis Classic (nom et compétence seulement : la ligne se retrouve par
--- le nom parmi les métiers connus).
local function openLine(char)
  local ui = C_TradeSkillUI
  local base = ui and ui.GetBaseProfessionInfo and ui.GetBaseProfessionInfo()
  local child = ui and ui.GetChildProfessionInfo and ui.GetChildProfessionInfo()
  if type(base) ~= "table" then base = nil end
  if type(child) ~= "table" then child = nil end
  local info = base or child
  if not info then
    local id, name, skill, max
    if ui and ui.GetTradeSkillLine then id, name, skill, max = ui.GetTradeSkillLine()
    elseif GetTradeSkillLine then name, skill, max = GetTradeSkillLine()
    elseif GetCraftDisplaySkillLine then name, skill, max = GetCraftDisplaySkillLine() end
    name = ns.plain(name)
    if not ns.plain(id) and name then
      for _, prof in pairs(char.professions or {}) do
        if prof.name == name then id = prof.line or prof.id end
      end
    end
    if id then info = { professionID = id, professionName = name, skillLevel = skill, maxSkillLevel = max } end
  end
  return info, child
end

local emptyReported = {}
-- Métiers sans recettes : leur fenêtre vide est normale (0.6.10 : la Pêche était notée comme une erreur).
local NO_RECIPES = { [356] = true, [182] = true, [393] = true } -- Pêche, Herboristerie, Dépeçage

--- Fenêtre d'un métier ouverte : liste des recettes apprises.
local function scanOpen(char)
  if C_TradeSkillUI and C_TradeSkillUI.IsTradeSkillLinked and C_TradeSkillUI.IsTradeSkillLinked() then return end -- métier d'un autre
  local info, child = openLine(char)
  local id = info and ns.plain(info.professionID)
  if type(id) ~= "number" or id <= 0 then return end
  local parent = positive(info.parentProfessionID, nil) or parentLine(id)
  local prof = entryFor(char, parent)
  prof.name = ns.plain(info.professionName) or prof.name
  -- La ligne d'extension porte la compétence ; la mère parfois 0 sur une base moderne.
  prof.skill = positive(child and child.skillLevel, positive(info.skillLevel, prof.skill))
  prof.max = positive(child and child.maxSkillLevel, positive(info.maxSkillLevel, prof.max))
  local recipes, api = modernRecipes()
  if not recipes or #recipes == 0 then
    local fallback, fallbackApi = classicRecipes()
    if fallback and (#fallback > 0 or not recipes) then recipes, api = fallback, fallbackApi end
  end
  if not recipes then
    ns.Store.LogError("professions.recipes", string.format(ns.L.RECIPES_NO_API, prof.name or tostring(id)))
    return
  end
  -- Une fenêtre ouverte sans aucune recette lue : soit un métier tout neuf, soit l'API ne répond pas comme on
  -- l'attend. On ne remplace pas une liste connue par rien, et on le note une fois par métier et par session.
  if #recipes == 0 and (prof.recipes and #prof.recipes > 0 or (prof.skill or 0) > 1) then
    if not emptyReported[parent] and not NO_RECIPES[parent] then
      emptyReported[parent] = true
      ns.Store.LogError("professions.recipes", string.format(ns.L.RECIPES_EMPTY, prof.name or tostring(id), api))
    end
    prof.read_at = ns.now()
    return
  end
  table.sort(recipes)
  prof.recipes = recipes
  prof.recipes_api = api
  prof.read_at = ns.now()
  ns.knownRecipes = ns.knownRecipes or {}
  for _, rid in ipairs(recipes) do ns.knownRecipes[rid] = true end
end

--- Le sort lancé est-il une recette ? D'abord les recettes lues dans les fenêtres, sinon la fiche de recette du
--- client (API moderne : toute recette apprise répond, fenêtre ouverte ou non). Jamais en combat : on ne
--- fabrique pas en combat, et les valeurs y sont secrètes.
function ns.IsRecipe(spellId)
  if type(spellId) ~= "number" then return false end
  if ns.knownRecipes and ns.knownRecipes[spellId] then return true end
  if ns.InCombat() or not (C_TradeSkillUI and C_TradeSkillUI.GetRecipeInfo) then return false end
  local ok, r = pcall(C_TradeSkillUI.GetRecipeInfo, spellId)
  if ok and type(r) == "table" and ns.plain(r.learned) then
    ns.knownRecipes = ns.knownRecipes or {}
    ns.knownRecipes[spellId] = true
    return true
  end
  return false
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
  -- TRADE_SKILL_UPDATE et CRAFT_* sont les événements de l'interface Classic (fenêtre d'enchantement à part).
  events = {
    SKILL_LINES_CHANGED = true, TRADE_SKILL_SHOW = true, TRADE_SKILL_LIST_UPDATE = true, TRADE_SKILL_UPDATE = true,
    CRAFT_SHOW = true, CRAFT_UPDATE = true,
  },
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
    if event ~= "SKILL_LINES_CHANGED" then
      ns.Debounce("professions:open", 1, function() ns.Safe("professions.open", scanOpen, char) end)
    end
  end,
  status = function(char)
    if available == false then return ns.L.NOT_AVAILABLE end
    local lines = {}
    for _, prof in pairs(char.professions or {}) do
      local label = (prof.name or tostring(prof.id)) .. " " .. tostring(prof.skill or "?")
      if prof.recipes then
        lines[#lines + 1] = string.format(ns.L.UP_TO_DATE,
          string.format("%s · %d recettes · %s", label, #prof.recipes, ns.UI.Ago(prof.read_at)))
      elseif prof.read_at then
        lines[#lines + 1] = "|cffffb84a" .. label .. " : fenêtre lue sans aucune recette, /mf erreurs|r"
      else
        lines[#lines + 1] = "|cffffb84a" .. label .. " : jamais lu, ouvre la fenêtre du métier|r"
      end
    end
    table.sort(lines)
    return #lines > 0 and table.concat(lines, "\n") or ns.L.NEVER_READ
  end,
})
