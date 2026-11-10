-- Carte du monde et minimap : un point couleur de classe par membre qui partage sa position (HereBeDragons-Pins :
-- cartes de zone, de continent et du monde ; minimap avec flottement au bord). Survol → infobulle (nom, niveau,
-- zone, talents, recherche de groupe, attaque en cours, âge) ; clic gauche → menu Inviter / Chuchoter. Les points
-- superposés (même endroit) sont regroupés dans l'infobulle et le menu. Anneau rouge pendant un appel à l'aide.
-- Les membres de mon groupe ou de mon raid n'ont pas de point : le jeu les affiche déjà, le nôtre ferait doublon.
-- Wanted : tête de mort rouge (8e marqueur de raid), plus grande que les points, avec la prime en chiffre, posée là où
-- l'ennemi a tué un membre ; elle pâlit puis disparaît au bout de WANTED_TTL s (Wanted.lua la rafraîchit).
local ADDON, ns = ...

local MapUI = {}
ns.MapUI = MapUI
local L = ns.L

local DOT = "Interface\\CharacterFrame\\TempPortraitAlphaMask" -- disque blanc, teinté par classe
local SKULLS = "Interface\\TargetingFrame\\UI-RaidTargetingIcons" -- planche des marqueurs de raid, crâne en case 8
local SKULL_COORDS = { 0.75, 1, 0.25, 0.5 }
local MAX_ROWS = 6
local ROW_HEIGHT = 48

local pinsLib -- HereBeDragons-Pins-2.0, résolu à la demande (absent dans les tests)
local function pins()
  if pinsLib == nil then pinsLib = (LibStub and LibStub("HereBeDragons-Pins-2.0", true)) or false end
  return pinsLib or nil
end
function MapUI.UsePins(lib) pinsLib = lib end -- tests

local icons = {} -- guid → { map = cadre carte, mini = cadre minimap }
local pool = {}
local menu

local function classColor(token)
  local c = RAID_CLASS_COLORS and token and RAID_CLASS_COLORS[token]
  if c then return c.r or 1, c.g or 1, c.b or 1 end
  return 1, 1, 1
end

local function coloredName(peer)
  return ns.ClassColored(peer.name, peer.class)
end

--- Membres au même endroit que `peer` (lui compris), triés par nom.
local function stacked(peer)
  local list = {}
  local limit = ns.Data.POSITION_STACK
  for _, other in pairs(ns.Positions.peers) do
    if other.map and other.map == peer.map and other.x and peer.x
      and math.abs(other.x - peer.x) < limit and math.abs(other.y - peer.y) < limit then
      list[#list + 1] = other
    end
  end
  table.sort(list, function(a, b) return (a.name or "") < (b.name or "") end)
  return list
end
MapUI.Stacked = stacked

local function alerting(peer)
  return peer.alert ~= nil and peer.alert.at >= ns.now() - ns.Data.ALERT_TTL
end

-- --- points --------------------------------------------------------------------------------------------

--- Clic droit laissé à la carte. Le jeu réserve SetPassThroughButtons hors combat (ADDON_ACTION_BLOCKED sinon,
--- sans nom de fonction sur Forever) ; or un point se crée quand une position ou une mort arrive, souvent en
--- combat : l'appel attend alors la fin du combat.
local function passRightClick(f)
  if not f.SetPassThroughButtons then return end
  ns.Defer(function() ns.Risky("SetPassThroughButtons", pcall, f.SetPassThroughButtons, f, "RightButton") end)
end

local function newIcon(size)
  local f = CreateFrame("Button", nil, UIParent)
  f:SetSize(size, size)
  f.ring = f:CreateTexture(nil, "BACKGROUND")
  f.ring:SetAllPoints()
  f.ring:SetTexture(DOT)
  f.ring:SetVertexColor(0, 0, 0, 0.85)
  f.dot = f:CreateTexture(nil, "ARTWORK")
  f.dot:SetPoint("CENTER")
  f.dot:SetSize(size - 4, size - 4)
  f.dot:SetTexture(DOT)
  f:EnableMouse(true)
  passRightClick(f)
  f:SetScript("OnEnter", function(self) MapUI.ShowTooltip(self.peer, self) end)
  f:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
  f:SetScript("OnMouseUp", function(self, button)
    if button == "LeftButton" and self.peer then MapUI.OpenMenu(self.peer) end
  end)
  return f
end

local function paint(icon, peer)
  icon.peer = peer
  icon.dot:SetVertexColor(classColor(peer.class))
  if alerting(peer) then icon.ring:SetVertexColor(1, 0.15, 0.15, 1) else icon.ring:SetVertexColor(0, 0, 0, 0.85) end
end

local function minimapWanted()
  return ns.db and ns.db.settings.minimapDots == true
end

--- Déjà dans mon groupe ou mon raid : le jeu affiche lui-même ces membres sur la carte et la minimap.
local function inMyGroup(peer)
  local name = peer.sender or peer.name
  if not name or name == "" then return false end
  if UnitInParty and UnitInParty(name) then return true end
  if UnitInRaid and UnitInRaid(name) then return true end
  return false
end
MapUI.InMyGroup = inMyGroup

function MapUI.Update(peer)
  local lib = pins()
  if not lib then return end
  if not (peer.map and peer.x and peer.y) or inMyGroup(peer) then
    MapUI.Remove(peer.guid)
    return
  end
  local pair = icons[peer.guid]
  if not pair then
    pair = table.remove(pool) or { map = newIcon(14), mini = newIcon(10) }
    icons[peer.guid] = pair
  end
  -- La bibliothèque n'enlève pas d'elle-même un point ré-ajouté (pin accumulé tant que la carte reste ouverte), et
  -- refuse une carte inconnue en laissant l'ancien point : on retire toujours avant de reposer. C'est elle qui montre
  -- et cache les icônes (surtout sur la minimap, selon la distance), on ne force pas Show().
  paint(pair.map, peer)
  lib:RemoveWorldMapIcon(ns, pair.map)
  if not lib:AddWorldMapIconMap(ns, pair.map, peer.map, peer.x, peer.y, HBD_PINS_WORLDMAP_SHOW_WORLD or 3) then
    MapUI.Remove(peer.guid)
    return
  end
  if lib.RemoveMinimapIcon then lib:RemoveMinimapIcon(ns, pair.mini) end
  pair.mini:Hide()
  if minimapWanted() and lib.AddMinimapIconMap then
    paint(pair.mini, peer)
    lib:AddMinimapIconMap(ns, pair.mini, peer.map, peer.x, peer.y, true, true)
  end
end

function MapUI.Remove(guid)
  local pair = icons[guid]
  if not pair then return end
  icons[guid] = nil
  local lib = pins()
  if lib then
    lib:RemoveWorldMapIcon(ns, pair.map)
    if lib.RemoveMinimapIcon then lib:RemoveMinimapIcon(ns, pair.mini) end
  end
  pair.map.peer, pair.mini.peer = nil, nil
  pair.map:Hide()
  pair.mini:Hide()
  pool[#pool + 1] = pair
end

function MapUI.Clear()
  for guid in pairs(icons) do MapUI.Remove(guid) end
  if menu then menu:Hide() end
end

--- Repose chaque point d'après les positions connues : retire ceux des membres entrés dans mon groupe, remet ceux des
--- membres qui l'ont quitté.
function MapUI.Refresh()
  if not ns.Positions then return end
  for _, peer in pairs(ns.Positions.peers) do MapUI.Update(peer) end
end

-- HereBeDragons-Pins réagit lui-même aux événements de carte (zoom de la minimap, changement de zone) : on pose le
-- marqueur pour qu'un refus du jeu survenu à ce moment-là soit attribuable à la bibliothèque. Le groupe qui change
-- (GROUP_ROSTER_UPDATE, en rafale) regroupe un seul rafraîchissement des points.
ns.RegisterCollector({
  name = "mapui",
  events = { MINIMAP_UPDATE_ZOOM = true, PLAYER_ENTERING_WORLD = true, ZONE_CHANGED_NEW_AREA = true, GROUP_ROSTER_UPDATE = true },
  onEvent = function(_, event)
    if event == "GROUP_ROSTER_UPDATE" then
      ns.Debounce("mapui:refresh", 1, function() ns.Safe("mapui.refresh", MapUI.Refresh) end)
    else
      ns.lastRisky = { name = "HereBeDragons " .. event, t = ns.now() }
    end
  end,
})

--- Case « Points aussi sur la minimap » : ajoute ou retire les points de la minimap sans toucher à la carte.
function MapUI.SetMinimap(on)
  ns.db.settings.minimapDots = on and true or false
  for guid, pair in pairs(icons) do
    if pair.map.peer then MapUI.Update(pair.map.peer) end
  end
end

-- --- infobulle --------------------------------------------------------------------------------------------

local function describe(tooltip, p)
  tooltip:AddDoubleLine(coloredName(p), string.format(L.LEVEL_SHORT, p.level or 0), 1, 1, 1, 0.8, 0.8, 0.8)
  local place = ns.Positions.Where(p)
  if place ~= "" then tooltip:AddLine(place, 0.85, 0.85, 0.85) end
  if p.spec and p.spec ~= "" then tooltip:AddLine(p.spec, 0.6, 0.8, 1) end
  if p.lfg and p.lfg ~= "" then tooltip:AddLine(string.format(L.LFG_SHORT, p.lfg), 1, 0.82, 0) end
  if alerting(p) then
    local attacker = p.alert.attacker ~= "" and ns.ClassColored(p.alert.attacker, p.alert.class) or L.ATTACKER_UNKNOWN
    tooltip:AddLine(string.format(L.ALERT_SHORT, attacker) .. " · " .. ns.UI.Ago(p.alert.at), 1, 0.3, 0.3)
  end
  tooltip:AddLine(ns.UI.Ago(p.at), 0.6, 0.6, 0.6)
end

function MapUI.ShowTooltip(peer, owner)
  if not peer or not GameTooltip then return end
  GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
  GameTooltip:ClearLines()
  local list = stacked(peer)
  if #list == 0 then list = { peer } end
  for i, p in ipairs(list) do
    if i > 1 then GameTooltip:AddLine(" ") end
    describe(GameTooltip, p)
  end
  GameTooltip:AddLine(L.MAP_CLICK_HINT, 0.5, 0.5, 0.5)
  GameTooltip:Show()
end

-- --- menu Inviter / Chuchoter ------------------------------------------------------------------------------

--- Libellé et disponibilité de l'entrée d'invitation : chef (ou assistant) → Inviter ; membre d'un groupe →
--- Suggérer l'invitation (le client transmet la demande au chef) ; déjà ensemble → grisé.
function MapUI.InviteState(peer)
  local name = peer.sender or peer.name
  if (UnitInParty and UnitInParty(name)) or (UnitInRaid and UnitInRaid(name)) then return L.MENU_IN_GROUP, false end
  if IsInGroup and IsInGroup() then
    local leads = (UnitIsGroupLeader and UnitIsGroupLeader("player"))
      or (UnitIsGroupAssistant and UnitIsGroupAssistant("player"))
    if not leads then return L.MENU_SUGGEST, true end
  end
  return L.MENU_INVITE, true
end

function MapUI.Invite(peer)
  local name = peer.sender or peer.name
  local api = (C_PartyInfo and C_PartyInfo.InviteUnit) or InviteUnit
  if api and name then pcall(api, name) end
end

function MapUI.Whisper(peer)
  local name = peer.sender or peer.name
  if ChatFrame_OpenChat and name then ChatFrame_OpenChat("/w " .. name .. " ", DEFAULT_CHAT_FRAME) end
end

local function buildMenu()
  menu = CreateFrame("Frame", "WoWForeverGuildeMenu", UIParent, "BackdropTemplate")
  menu:SetSize(236, ROW_HEIGHT + 16)
  menu:SetFrameStrata("TOOLTIP")
  menu:EnableMouse(true)
  if menu.SetClampedToScreen then menu:SetClampedToScreen(true) end
  if menu.SetBackdrop then
    menu:SetBackdrop({
      bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark",
      edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", edgeSize = 14,
      insets = { left = 4, right = 4, top = 4, bottom = 4 },
    })
  end
  menu.rows = {}
  for i = 1, MAX_ROWS do
    local row = {}
    row.name = menu:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    row.name:SetPoint("TOPLEFT", 12, -10 - (i - 1) * ROW_HEIGHT)
    row.name:SetWidth(212)
    row.name:SetJustifyH("LEFT")
    row.invite = ns.UI.MakeButton(menu, L.MENU_INVITE, 128)
    row.invite:SetPoint("TOPLEFT", 10, -28 - (i - 1) * ROW_HEIGHT)
    row.invite:SetScript("OnClick", function(self) MapUI.Invite(self.peer) menu:Hide() end)
    row.whisper = ns.UI.MakeButton(menu, L.MENU_WHISPER, 86)
    row.whisper:SetPoint("LEFT", row.invite, "RIGHT", 4, 0)
    row.whisper:SetScript("OnClick", function(self) MapUI.Whisper(self.peer) menu:Hide() end)
    menu.rows[i] = row
  end
  -- Se ferme avec Échap, quand la carte se ferme, ou 1,5 s après que la souris l'a quitté.
  tinsert(UISpecialFrames, "WoWForeverGuildeMenu")
  if WorldMapFrame and WorldMapFrame.HookScript then WorldMapFrame:HookScript("OnHide", function() menu:Hide() end) end
  menu.away = 0
  menu:SetScript("OnUpdate", function(self, elapsed)
    if self.IsMouseOver and self:IsMouseOver() then self.away = 0 return end
    self.away = self.away + (elapsed or 0)
    if self.away > 1.5 then self:Hide() end
  end)
  menu:SetScript("OnShow", function(self) self.away = 0 end)
  menu:Hide()
end

--- Ouvre le menu pour `peer` (position reçue, ou membre de la liste : { name, sender, level, class }).
function MapUI.OpenMenu(peer)
  if not menu then buildMenu() end
  local list = peer.map and stacked(peer) or {}
  if #list == 0 then list = { peer } end
  for i, row in ipairs(menu.rows) do
    local p = list[i]
    if p then
      row.name:SetText(coloredName(p) .. " |cff9a9a9a" .. string.format(L.LEVEL_SHORT, p.level or 0) .. "|r")
      local label, can = MapUI.InviteState(p)
      row.invite:SetText(label)
      if row.invite.SetEnabled then row.invite:SetEnabled(can) end
      row.invite.peer, row.whisper.peer = p, p
      row.name:Show() row.invite:Show() row.whisper:Show()
    else
      row.name:Hide() row.invite:Hide() row.whisper:Hide()
    end
  end
  local shown = math.min(#list, MAX_ROWS)
  menu:SetSize(236, shown * ROW_HEIGHT + 16)
  if GetCursorPosition and UIParent and UIParent.GetEffectiveScale then
    local x, y = GetCursorPosition()
    local scale = UIParent:GetEffectiveScale()
    menu:ClearAllPoints()
    menu:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", x / scale + 8, y / scale - 8)
  end
  if GameTooltip then GameTooltip:Hide() end
  menu:Show()
end

function MapUI.Menu() return menu end -- tests

-- --- têtes mises à prix ---------------------------------------------------------------------------------------

local wantedIcons = {} -- clé d'ennemi → { map = cadre carte, mini = cadre minimap }
local wantedPool = {}

local function newSkull(size)
  local f = CreateFrame("Button", nil, UIParent)
  f:SetSize(size, size)
  f.skull = f:CreateTexture(nil, "ARTWORK")
  f.skull:SetAllPoints()
  f.skull:SetTexture(SKULLS)
  f.skull:SetTexCoord(unpack(SKULL_COORDS))
  f.skull:SetVertexColor(1, 0.25, 0.25)
  f.points = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  f.points:SetPoint("LEFT", f, "RIGHT", 1, 0)
  f.points:SetTextColor(1, 0.3, 0.3)
  f:EnableMouse(true)
  passRightClick(f)
  f:SetScript("OnEnter", function(self) MapUI.ShowWantedTooltip(self.entry, self) end)
  f:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
  return f
end

local function paintSkull(icon, entry, alpha)
  icon.entry = entry
  icon.points:SetText(tostring(entry.points or 0))
  icon:SetAlpha(alpha)
end

--- Pose (ou déplace) la tête de mort d'un ennemi à sa dernière position connue ; la retire si elle est trop vieille,
--- sans coordonnées, ou si les alertes Wanted sont décochées. Opacité : pleine au moment du kill, 40 % à la fin.
function MapUI.UpdateWanted(entry)
  local lib = pins()
  if not lib or not ns.Wanted then return end
  local key = ns.Wanted.Key(entry.name)
  local now = ns.now()
  if not (ns.db and ns.db.settings.wantedAlerts) or not ns.Wanted.Fresh(entry, now) then
    MapUI.RemoveWanted(key)
    return
  end
  local last = entry.last
  local pair = wantedIcons[key]
  if not pair then
    pair = table.remove(wantedPool) or { map = newSkull(22), mini = newSkull(14) }
    wantedIcons[key] = pair
  end
  local alpha = 1 - 0.6 * math.min(1, math.max(0, (now - (last.t or now)) / ns.Data.WANTED_TTL))
  paintSkull(pair.map, entry, alpha)
  lib:RemoveWorldMapIcon(ns, pair.map)
  if not lib:AddWorldMapIconMap(ns, pair.map, last.map, last.x, last.y, HBD_PINS_WORLDMAP_SHOW_WORLD or 3) then
    MapUI.RemoveWanted(key)
    return
  end
  if lib.RemoveMinimapIcon then lib:RemoveMinimapIcon(ns, pair.mini) end
  pair.mini:Hide()
  if minimapWanted() and lib.AddMinimapIconMap then
    paintSkull(pair.mini, entry, alpha)
    lib:AddMinimapIconMap(ns, pair.mini, last.map, last.x, last.y, true, true)
  end
end

function MapUI.RemoveWanted(key)
  local pair = wantedIcons[key]
  if not pair then return end
  wantedIcons[key] = nil
  local lib = pins()
  if lib then
    lib:RemoveWorldMapIcon(ns, pair.map)
    if lib.RemoveMinimapIcon then lib:RemoveMinimapIcon(ns, pair.mini) end
  end
  pair.map.entry, pair.mini.entry = nil, nil
  pair.map:Hide()
  pair.mini:Hide()
  wantedPool[#wantedPool + 1] = pair
end

function MapUI.WantedIcons() return wantedIcons end -- tests

--- Infobulle d'une tête de mort : nom coloré, classe, prime, kills de la guilde, dernière victime ici, victimes.
function MapUI.ShowWantedTooltip(entry, owner)
  if not entry or not GameTooltip then return end
  GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
  GameTooltip:ClearLines()
  GameTooltip:AddDoubleLine(ns.ClassColored(entry.name, entry.class), L.WANTED_TAG, 1, 1, 1, 1, 0.3, 0.3)
  local class = ns.ClassLabel(entry.class)
  local prime = string.format(L.WANTED_PRIME, entry.points or 0)
  GameTooltip:AddLine(class ~= "" and (class .. " · " .. prime) or prime, 1, 0.82, 0)
  if (entry.kills or 0) > 0 then GameTooltip:AddLine(string.format(L.WANTED_KILLED_BY_GUILD, entry.kills), 0.6, 0.8, 1) end
  local last = entry.last
  if last then
    if last.kind == "kill" then
      GameTooltip:AddLine(string.format(L.WANTED_KILLED_HERE, ns.ClassColored(last.by or "?", last.byClass), ns.UI.Ago(last.t)), 0.6, 0.9, 0.6)
    elseif last.kind == "seen" then
      GameTooltip:AddLine(string.format(L.WANTED_LAST_SEEN, ns.UI.Ago(last.t)), 0.85, 0.85, 0.85)
    else
      local victim = ns.ClassColored(last.victim or "?", last.victimClass)
      GameTooltip:AddLine(string.format(L.WANTED_HERE, victim, ns.UI.Ago(last.t)), 0.85, 0.85, 0.85)
    end
    local place = ns.Wanted.Where(entry)
    if place ~= "" then GameTooltip:AddLine(place, 0.6, 0.6, 0.6) end
  end
  local names = {}
  for i = #(entry.victims or {}), math.max(1, #(entry.victims or {}) - 4), -1 do
    local v = entry.victims[i]
    if v then names[#names + 1] = v.name or "?" end
  end
  if #names > 0 then GameTooltip:AddLine(string.format(L.WANTED_VICTIMS, table.concat(names, ", ")), 0.6, 0.6, 0.6) end
  GameTooltip:Show()
end
