-- Carte du monde : un point couleur de classe par membre qui partage sa position (HereBeDragons-Pins : cartes de
-- zone, de continent et du monde). Survol → infobulle (nom, niveau, zone, talents, âge) ; clic gauche → menu
-- Inviter / Chuchoter. Les points superposés (même endroit) sont regroupés dans l'infobulle et le menu.
local ADDON, ns = ...

local MapUI = {}
ns.MapUI = MapUI
local L = ns.L

local DOT = "Interface\\CharacterFrame\\TempPortraitAlphaMask" -- disque blanc, teinté par classe
local MAX_ROWS = 6
local ROW_HEIGHT = 48

local pinsLib -- HereBeDragons-Pins-2.0, résolu à la demande (absent dans les tests)
local function pins()
  if pinsLib == nil then pinsLib = (LibStub and LibStub("HereBeDragons-Pins-2.0", true)) or false end
  return pinsLib or nil
end
function MapUI.UsePins(lib) pinsLib = lib end -- tests

local icons = {} -- guid → cadre du point
local pool = {}
local menu

local function classColor(token)
  local c = RAID_CLASS_COLORS and token and RAID_CLASS_COLORS[token]
  if c then return c.r or 1, c.g or 1, c.b or 1, c.colorStr or "ffffffff" end
  return 1, 1, 1, "ffffffff"
end

local function coloredName(peer)
  local _, _, _, hex = classColor(peer.class)
  return "|c" .. hex .. (peer.name or "?") .. "|r"
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

-- --- points --------------------------------------------------------------------------------------------

local function newIcon()
  local f = CreateFrame("Button", nil, UIParent)
  f:SetSize(14, 14)
  f.ring = f:CreateTexture(nil, "BACKGROUND")
  f.ring:SetAllPoints()
  f.ring:SetTexture(DOT)
  f.ring:SetVertexColor(0, 0, 0, 0.85)
  f.dot = f:CreateTexture(nil, "ARTWORK")
  f.dot:SetPoint("CENTER")
  f.dot:SetSize(10, 10)
  f.dot:SetTexture(DOT)
  f:EnableMouse(true)
  if f.SetPassThroughButtons then pcall(f.SetPassThroughButtons, f, "RightButton") end -- clic droit : la carte
  f:SetScript("OnEnter", function(self) MapUI.ShowTooltip(self.peer, self) end)
  f:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
  f:SetScript("OnMouseUp", function(self, button)
    if button == "LeftButton" and self.peer then MapUI.OpenMenu(self.peer) end
  end)
  return f
end

function MapUI.Update(peer)
  local lib = pins()
  if not lib then return end
  if not (peer.map and peer.x and peer.y) then
    MapUI.Remove(peer.guid)
    return
  end
  local icon = icons[peer.guid]
  if not icon then
    icon = table.remove(pool) or newIcon()
    icons[peer.guid] = icon
  end
  icon.peer = peer
  local r, g, b = classColor(peer.class)
  icon.dot:SetVertexColor(r, g, b)
  icon:Show()
  lib:AddWorldMapIconMap(ns, icon, peer.map, peer.x, peer.y, HBD_PINS_WORLDMAP_SHOW_WORLD or 3)
end

function MapUI.Remove(guid)
  local icon = icons[guid]
  if not icon then return end
  icons[guid] = nil
  local lib = pins()
  if lib then lib:RemoveWorldMapIcon(ns, icon) end
  icon.peer = nil
  icon:Hide()
  pool[#pool + 1] = icon
end

function MapUI.Clear()
  for guid in pairs(icons) do MapUI.Remove(guid) end
  if menu then menu:Hide() end
end

-- --- infobulle --------------------------------------------------------------------------------------------

local function where(peer)
  local text = peer.zone or ""
  if peer.sub and peer.sub ~= "" and peer.sub ~= peer.zone then
    text = text ~= "" and (text .. " · " .. peer.sub) or peer.sub
  end
  return text
end

function MapUI.ShowTooltip(peer, owner)
  if not peer or not GameTooltip then return end
  GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
  GameTooltip:ClearLines()
  for i, p in ipairs(stacked(peer)) do
    if i > 1 then GameTooltip:AddLine(" ") end
    GameTooltip:AddDoubleLine(coloredName(p), string.format(L.LEVEL_SHORT, p.level or 0), 1, 1, 1, 0.8, 0.8, 0.8)
    local place = where(p)
    if place ~= "" then GameTooltip:AddLine(place, 0.85, 0.85, 0.85) end
    if p.spec and p.spec ~= "" then GameTooltip:AddLine(p.spec, 0.6, 0.8, 1) end
    GameTooltip:AddLine(ns.UI.Ago(p.at), 0.6, 0.6, 0.6)
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

function MapUI.OpenMenu(peer)
  if not menu then buildMenu() end
  local list = stacked(peer)
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
