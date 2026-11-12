-- Onglet « Guilde en jeu » de la fenêtre /mf (/mf qui) : membres en ligne regroupés par zone d'après le roster de guilde (tout le
-- monde, même sans addon), enrichis des positions partagées (sous-zone, talents, recherche de groupe, attaque en
-- cours). Section « Cherchent un groupe » en tête. Champ pour diffuser sa propre recherche. Clic sur un nom : menu
-- Inviter / Chuchoter ; survol : infobulle quand la position est connue.
local ADDON, ns = ...

local RosterUI = {}
ns.RosterUI = RosterUI
local L = ns.L

local COLUMNS = {
  { L.COL_NAME, 0, 190 }, { L.COL_LEVEL, 194, 34, "RIGHT" }, { L.COL_PLACE, 244, 170 }, { L.COL_INFO, 418, 230 },
}
local frame
local rows = {}
local pending = false

local function requestRoster()
  local api = (C_GuildInfo and C_GuildInfo.GuildRoster) or GuildRoster
  if api then ns.Risky("GuildRoster", pcall, api) end
end

local function header(label, count)
  return "|cffffd100" .. label .. "|r |cff9a9a9a(" .. tostring(count) .. ")|r"
end

local function line(m)
  local parts = { ns.ClassColored(m.name, m.class) .. " |cff9a9a9a" .. tostring(m.level or 0) .. "|r" }
  local p = m.peer
  if p then
    if p.sub and p.sub ~= "" and p.sub ~= p.zone then parts[#parts + 1] = "|cffbcbcbc" .. p.sub .. "|r" end
    if p.spec and p.spec ~= "" then parts[#parts + 1] = "|cff9accff" .. p.spec .. "|r" end
    if p.lfg and p.lfg ~= "" then parts[#parts + 1] = "|cffffd100" .. string.format(L.LFG_SHORT, p.lfg) .. "|r" end
    if p.alert and p.alert.at >= ns.now() - ns.Data.ALERT_TTL then
      local attacker = p.alert.attacker ~= "" and p.alert.attacker or L.ATTACKER_UNKNOWN
      parts[#parts + 1] = "|cffff4d4d" .. L.ICON_SWORDS .. " " .. string.format(L.ALERT_SHORT, attacker) .. "|r"
    end
  end
  return "  " .. table.concat(parts, " · ")
end

--- Les cellules d'un membre : nom à sa couleur de classe, niveau, sous-zone (la zone est le titre du groupe),
--- puis ce que sa position partagée ajoute : talents, recherche de groupe, attaque en cours.
local function cells(m)
  local p = m.peer
  local place, info = "", {}
  if p then
    if p.sub and p.sub ~= "" and p.sub ~= p.zone then place = "|cffbcbcbc" .. p.sub .. "|r" end
    if p.alert and p.alert.at >= ns.now() - ns.Data.ALERT_TTL then
      local attacker = p.alert.attacker ~= "" and p.alert.attacker or L.ATTACKER_UNKNOWN
      info[#info + 1] = "|cffff4d4d" .. L.ICON_SWORDS .. " " .. string.format(L.ALERT_SHORT, attacker) .. "|r"
    end
    if p.lfg and p.lfg ~= "" then info[#info + 1] = "|cffffd100" .. string.format(L.LFG_SHORT, p.lfg) .. "|r" end
    if p.spec and p.spec ~= "" then info[#info + 1] = "|cff9accff" .. p.spec .. "|r" end
  end
  return { ns.ClassColored(m.name, m.class), "|cff9a9a9a" .. tostring(m.level or 0) .. "|r", place, table.concat(info, " · ") }
end

local function row(i)
  local r = rows[i]
  if not r then
    r = ns.UI.MakeRow(frame.content, COLUMNS, i)
    r:SetScript("OnClick", function(self) if self.member then ns.MapUI.OpenMenu(self.member) end end)
    r:SetScript("OnEnter", function(self)
      if self.member and self.member.peer then ns.MapUI.ShowTooltip(self.member.peer, self) end
    end)
    r:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    rows[i] = r
  end
  return r
end

--- Lignes à afficher : { text, member?, cells? } ; un titre de groupe n'a que son texte. Exposé pour les tests.
function RosterUI.Lines()
  local members = ns.Positions.Members()
  local myZone = (GetZoneText and GetZoneText()) or ""
  local onlyMine = ns.db.settings.rosterMyZone
  local myGuid = ns.char and ns.char.guid
  local groups, order, lfg = {}, {}, {}
  for _, m in ipairs(members) do
    if m.guid ~= myGuid then
      if m.peer and m.peer.lfg and m.peer.lfg ~= "" then lfg[#lfg + 1] = m end
      if not onlyMine or m.zone == myZone then
        local zone = m.zone ~= "" and m.zone or L.WHERE_UNKNOWN
        if not groups[zone] then
          groups[zone] = {}
          order[#order + 1] = zone
        end
        table.insert(groups[zone], m)
      end
    end
  end
  table.sort(order, function(a, b)
    if a == myZone then return true elseif b == myZone then return false end
    return a < b
  end)
  local byLevel = function(a, b)
    if (a.level or 0) ~= (b.level or 0) then return (a.level or 0) > (b.level or 0) end
    return (a.name or "") < (b.name or "")
  end
  local lines = {}
  if #lfg > 0 then
    table.sort(lfg, byLevel)
    lines[#lines + 1] = { text = header(L.ROSTER_LFG_SECTION, #lfg) }
    for _, m in ipairs(lfg) do lines[#lines + 1] = { text = line(m), member = m, cells = cells(m) } end
  end
  for _, zone in ipairs(order) do
    local list = groups[zone]
    table.sort(list, byLevel)
    lines[#lines + 1] = { text = header(zone, #list) }
    for _, m in ipairs(list) do lines[#lines + 1] = { text = line(m), member = m, cells = cells(m) } end
  end
  return lines
end

function RosterUI.Render()
  if not frame or not ns.UI.Shown("roster") then return end
  local lines = RosterUI.Lines()
  for i, l in ipairs(lines) do
    local r = row(i)
    ns.UI.FillRow(r, l)
    r.member = l.member
    r:Show()
  end
  for i = #lines + 1, #rows do
    rows[i]:Hide()
    rows[i].member = nil
  end
  frame.content:SetSize(ns.UI.LIST_WIDTH, math.max(#lines, 1) * ns.UI.ROW_HEIGHT)
  if #lines == 0 then frame.empty:Show() else frame.empty:Hide() end
  if not (frame.lfg.HasFocus and frame.lfg:HasFocus()) then frame.lfg:SetText(ns.Positions.lfg or "") end
end

--- Rafraîchissement regroupé (les positions arrivent en rafale).
function RosterUI.Refresh()
  if not frame or not ns.UI.Shown("roster") or pending then return end
  pending = true
  C_Timer.After(ns.Data.ROSTER_REFRESH, function()
    pending = false
    ns.Safe("roster.render", RosterUI.Render)
  end)
end

local function build(panel)
  frame = panel
  frame.lfgLabel = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  frame.lfgLabel:SetPoint("TOPLEFT", 16, -46)
  frame.lfgLabel:SetText(L.ROSTER_LFG_LABEL)
  frame.lfg = CreateFrame("EditBox", nil, frame, "InputBoxTemplate")
  frame.lfg:SetSize(200, 20)
  frame.lfg:SetPoint("LEFT", frame.lfgLabel, "RIGHT", 10, 0)
  frame.lfg:SetAutoFocus(false)
  if frame.lfg.SetMaxLetters then frame.lfg:SetMaxLetters(60) end
  frame.lfg:SetScript("OnEnterPressed", function(self)
    ns.Positions.SetLFG(self:GetText())
    self:ClearFocus()
  end)
  frame.lfg:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  frame.lfgHint = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  frame.lfgHint:SetPoint("TOPLEFT", 16, -68)
  frame.lfgHint:SetText(L.ROSTER_LFG_HINT)
  frame.myZone = ns.UI.MakeCheck(frame, L.ROSTER_MY_ZONE,
    function() return ns.db.settings.rosterMyZone end,
    function(on) ns.db.settings.rosterMyZone = on RosterUI.Render() end)
  frame.myZone:SetPoint("TOPRIGHT", -150, -42)

  frame.scroll = CreateFrame("ScrollFrame", nil, frame, "UIPanelScrollFrameTemplate")
  ns.UI.MakeColumnHeaders(frame, COLUMNS, -90)
  frame.scroll:SetPoint("TOPLEFT", 16, -108)
  frame.scroll:SetPoint("BOTTOMRIGHT", -36, 40)
  frame.content = CreateFrame("Frame", nil, frame.scroll)
  frame.content:SetSize(ns.UI.LIST_WIDTH, ns.UI.ROW_HEIGHT)
  frame.scroll:SetScrollChild(frame.content)
  frame.empty = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  frame.empty:SetPoint("TOPLEFT", 20, -114)
  frame.empty:SetText(L.ROSTER_EMPTY)
  frame.sos = ns.UI.MakeButton(frame, L.SOS_BUTTON, 170)
  frame.sos:SetPoint("BOTTOMRIGHT", -16, 12)
  frame.sos:SetScript("OnClick", function() ns.Positions.SOS() end)
  frame.hint = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  frame.hint:SetPoint("BOTTOMLEFT", 16, 18)
  frame.hint:SetText(L.ROSTER_HINT)
end

ns.UI.AddTab({
  key = "roster", order = 1, label = L.ROSTER_TITLE, name = "WoWForeverGuildeRoster", build = build,
  show = function()
    requestRoster()
    ns.Safe("roster.render", RosterUI.Render)
  end,
})

function RosterUI.Toggle()
  ns.UI.Toggle("roster")
end

function RosterUI.Frame() return frame end -- tests
