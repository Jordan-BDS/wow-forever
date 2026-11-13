-- NameplateUI : tête de mort sur la plaque de nom d'un joueur adverse recherché (prime à encaisser).
-- À l'apparition d'une plaque (NAME_PLATE_UNIT_ADDED) on lit l'unité : un joueur attaquable dont le nom est au
-- tableau Wanted avec une prime reçoit une icône ancrée au-dessus de sa plaque, retirée quand la plaque disparaît
-- (le jeu recycle les plaques d'un joueur à l'autre). Les plaques affichées sont relues quand le tableau change
-- (nouvelle prime, prime encaissée), à la fin d'un combat et quand on coche ou décoche le réglage.
-- En combat le nom d'un adversaire peut être secret : on le retrouve par l'identifiant de l'unité s'il a été lu
-- dans les SEEN_PLAYERS_TTL dernières secondes ; sinon la plaque reste sans icône jusqu'à la fin du combat.
-- Comme le reste du Wanted, rien en champ de bataille ni en arène. Si le jeu refuse l'ancrage sur une plaque,
-- l'erreur est notée une fois (où = « plaques ») et dite par `/mf api`.
local ADDON, ns = ...

local Nameplates = {}
ns.Nameplates = Nameplates

local SKULLS = "Interface\\TargetingFrame\\UI-RaidTargetingIcons" -- planche des marqueurs de raid, crâne en case 8
local SKULL_COORDS = { 0.75, 1, 0.25, 0.5 }
local SIZE = 20
local OFFSET_Y = 2 -- au-dessus de la plaque

local marks = {} -- jeton d'unité (« nameplate3 ») → icône posée
local pool = {}
local refused = nil -- première erreur d'ancrage de la session

--- Valeur lue sous protection : nil si l'appel échoue ou si le jeu la garde secrète (en combat).
local function read(fn, ...)
  if type(fn) ~= "function" then return nil end
  local ok, value = pcall(fn, ...)
  if not ok then return nil end
  return ns.plain(value)
end

local function enabled()
  return ns.db ~= nil and ns.db.settings.bountyPlates == true and not ns.InBattleground()
end

--- L'entrée Wanted du joueur adverse derrière ce jeton, s'il a une prime à encaisser ; nil sinon.
local function bountyOn(token)
  if not read(UnitExists, token) then return nil end
  if read(UnitIsPlayer, token) == false then return nil end
  if read(UnitCanAttack, "player", token) == false or read(UnitIsFriend, "player", token) == true then return nil end
  local name = ns.UnitDisplayName(token)
  if not name then
    local guid = read(UnitGUID, token)
    name = type(guid) == "string" and ns.SeenPlayer and ns.SeenPlayer(nil, guid) or nil
  end
  if not name then return nil end
  local entry = ns.Wanted.Match(name)
  return ns.Wanted.Active(entry) and entry or nil
end

local function plateFor(token)
  local plate = read(C_NamePlate and C_NamePlate.GetNamePlateForUnit, token)
  return type(plate) == "table" and plate or nil
end

local function newIcon()
  local f = CreateFrame("Frame", nil, UIParent)
  f:SetSize(SIZE, SIZE)
  f.skull = f:CreateTexture(nil, "OVERLAY")
  f.skull:SetAllPoints()
  f.skull:SetTexture(SKULLS)
  f.skull:SetTexCoord(unpack(SKULL_COORDS))
  f.skull:SetVertexColor(1, 0.25, 0.25)
  f:Hide()
  return f
end

local function attach(icon, plate)
  icon:SetParent(plate)
  icon:ClearAllPoints()
  icon:SetPoint("BOTTOM", plate, "TOP", 0, OFFSET_Y)
  icon.plate = plate
end

local function release(token)
  local icon = marks[token]
  if not icon then return end
  marks[token] = nil
  icon.plate, icon.entry = nil, nil
  pcall(function()
    icon:Hide()
    icon:ClearAllPoints()
    icon:SetParent(UIParent)
  end)
  pool[#pool + 1] = icon
end

--- Pose, garde ou retire l'icône de la plaque de ce jeton, d'après ce qu'on lit de l'unité maintenant.
function Nameplates.Update(token)
  if type(token) ~= "string" then return end
  local entry = enabled() and bountyOn(token) or nil
  local plate = entry and plateFor(token) or nil
  if not plate then
    release(token)
    return
  end
  local icon = marks[token]
  if not icon then
    icon = table.remove(pool) or newIcon()
    marks[token] = icon
  end
  if icon.plate ~= plate then
    local ok, err = pcall(attach, icon, plate)
    if not ok then
      release(token)
      if not refused then
        refused = tostring(err)
        ns.Store.LogError("plaques", err)
      end
      return
    end
  end
  icon.entry = entry
  icon:Show()
end

--- Relit toutes les plaques affichées, et celles qui portent encore une icône.
function Nameplates.Refresh()
  local tokens, seen = {}, {}
  local plates = read(C_NamePlate and C_NamePlate.GetNamePlates)
  if type(plates) == "table" then
    for _, plate in ipairs(plates) do
      local token = type(plate) == "table" and ns.plain(plate.namePlateUnitToken)
      if type(token) == "string" and not seen[token] then
        seen[token] = true
        tokens[#tokens + 1] = token
      end
    end
  end
  for token in pairs(marks) do
    if not seen[token] then tokens[#tokens + 1] = token end
  end
  for _, token in ipairs(tokens) do Nameplates.Update(token) end
end

--- Case « Tête de mort sur la plaque de nom d'un ennemi recherché ».
function Nameplates.SetEnabled(on)
  ns.db.settings.bountyPlates = on and true or false
  Nameplates.Refresh()
end

--- L'icône posée sur ce jeton, nil s'il n'y en a pas (tests, diagnostic).
function Nameplates.Mark(token)
  return marks[token]
end

ns.RegisterCollector({
  name = "nameplates",
  events = {
    NAME_PLATE_UNIT_ADDED = true, NAME_PLATE_UNIT_REMOVED = true, PLAYER_REGEN_ENABLED = true,
    PLAYER_ENTERING_WORLD = true,
  },
  onEvent = function(char, event, ...)
    if event == "NAME_PLATE_UNIT_ADDED" then
      Nameplates.Update(ns.plain((...)))
    elseif event == "NAME_PLATE_UNIT_REMOVED" then
      local token = ns.plain((...))
      if type(token) == "string" then release(token) end
    else
      Nameplates.Refresh()
    end
  end,
  status = function()
    local n = 0
    for _ in pairs(marks) do n = n + 1 end
    local state = (ns.db and ns.db.settings.bountyPlates) and "" or " · réglage décoché"
    return string.format("%d plaque(s) marquée(s)%s%s", n, state, refused and (" · ancrage refusé : " .. refused) or "")
  end,
})
