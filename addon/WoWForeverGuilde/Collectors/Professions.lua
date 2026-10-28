-- Métiers : compétence dès la connexion ; recettes connues seulement quand la fenêtre du métier est ouverte.
local ADDON, ns = ...

local function entryFor(char, skillLine)
  char.professions = char.professions or {}
  local key = tostring(skillLine)
  char.professions[key] = char.professions[key] or { id = skillLine }
  return char.professions[key]
end

--- Métiers connus (sans recettes) : GetProfessions (moderne) → GetProfessionInfo.
local function scanKnown(char)
  if not (GetProfessions and GetProfessionInfo) then return end
  local seen = {}
  for _, index in ipairs({ GetProfessions() }) do
    if type(index) == "number" then
      local name, _, skill, max, _, _, skillLine = GetProfessionInfo(index)
      if skillLine then
        local prof = entryFor(char, skillLine)
        prof.name, prof.skill, prof.max = name, ns.plain(skill), ns.plain(max)
        seen[tostring(skillLine)] = true
      end
    end
  end
  -- Un métier abandonné disparaît.
  for key in pairs(char.professions or {}) do
    if not seen[key] then char.professions[key] = nil end
  end
  char.professions_at = ns.now()
end

--- Fenêtre d'un métier ouverte : liste des recettes apprises.
local function scanOpen(char)
  if not C_TradeSkillUI then return end
  local info = C_TradeSkillUI.GetBaseProfessionInfo and C_TradeSkillUI.GetBaseProfessionInfo()
  if not info and C_TradeSkillUI.GetTradeSkillLine then
    local id, name, skill, max = C_TradeSkillUI.GetTradeSkillLine()
    info = id and { professionID = id, professionName = name, skillLevel = skill, maxSkillLevel = max } or nil
  end
  if not info or not info.professionID then return end
  if C_TradeSkillUI.IsTradeSkillLinked and C_TradeSkillUI.IsTradeSkillLinked() then return end -- métier d'un autre
  local prof = entryFor(char, info.professionID)
  prof.name = info.professionName or prof.name
  prof.skill = ns.plain(info.skillLevel) or prof.skill
  prof.max = ns.plain(info.maxSkillLevel) or prof.max
  local recipes = {}
  for _, recipeId in ipairs(C_TradeSkillUI.GetAllRecipeIDs() or {}) do
    local r = C_TradeSkillUI.GetRecipeInfo(recipeId)
    if r and r.learned then recipes[#recipes + 1] = recipeId end
  end
  table.sort(recipes)
  prof.recipes = recipes
  prof.read_at = ns.now()
  ns.knownRecipes = ns.knownRecipes or {}
  for _, id in ipairs(recipes) do ns.knownRecipes[id] = true end
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
