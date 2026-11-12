-- Onglet « Wanted » de la fenêtre /mf (/mf wanted) : les têtes mises à prix, prime décroissante. Une ligne par
-- ennemi : nom coloré par classe, classe, prime, kills de la guilde (lot 2), dernière victime, lieu et âge ; survol :
-- la même infobulle que la tête de mort sur la carte.
local ADDON, ns = ...

local WantedUI = {}
ns.WantedUI = WantedUI
local L = ns.L

local ROW = 16
local WIDTH = 500
local frame
local rows = {}
local pending = false

local function line(entry)
  local parts = { L.ICON_SKULL .. " " .. ns.ClassColored(entry.name, entry.class) }
  local class = ns.ClassLabel(entry.class)
  if class ~= "" then parts[#parts + 1] = "|cff9a9a9a" .. class .. "|r" end
  parts[#parts + 1] = "|cffffd100" .. string.format(L.WANTED_PRIME, ns.Points(entry.points)) .. "|r"
  if (entry.kills or 0) > 0 then parts[#parts + 1] = "|cff9accff" .. string.format(L.WANTED_KILLED_BY_GUILD, entry.kills) .. "|r" end
  local last = entry.last
  if last then
    local place = ns.Wanted.Where(entry)
    place = place ~= "" and place or L.WHERE_UNKNOWN
    if last.kind == "kill" then
      parts[#parts + 1] = "|cff9ad19a" .. string.format(L.WANTED_LAST_KILL, ns.ClassColored(last.by or "?", last.byClass), place, ns.UI.Ago(last.t)) .. "|r"
    elseif last.kind == "seen" then
      parts[#parts + 1] = "|cffbcbcbc" .. string.format(L.WANTED_LAST_SEEN, ns.UI.Ago(last.t)) .. "|r"
    else
      parts[#parts + 1] = "|cffbcbcbc" .. string.format(L.WANTED_LAST, ns.ClassColored(last.victim or "?", last.victimClass), place, ns.UI.Ago(last.t)) .. "|r"
    end
  end
  return "  " .. table.concat(parts, " · ")
end

local function row(i)
  local r = rows[i]
  if not r then
    r = CreateFrame("Button", nil, frame.content)
    r:SetSize(WIDTH, ROW)
    r:SetPoint("TOPLEFT", 0, -(i - 1) * ROW)
    r.text = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.text:SetPoint("LEFT", 0, 0)
    r.text:SetWidth(WIDTH)
    r.text:SetJustifyH("LEFT")
    r:SetScript("OnEnter", function(self) if self.entry then ns.MapUI.ShowWantedTooltip(self.entry, self) end end)
    r:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    rows[i] = r
  end
  return r
end

--- Lignes à afficher : { text, entry? }. Exposé pour les tests.
function WantedUI.Lines()
  local list = ns.Wanted.Sorted()
  local lines = {}
  if #list == 0 then return lines end
  lines[#lines + 1] = { text = "|cffffd100" .. L.WANTED_SECTION .. "|r |cff9a9a9a(" .. #list .. ")|r" }
  for _, entry in ipairs(list) do lines[#lines + 1] = { text = line(entry), entry = entry } end
  return lines
end

function WantedUI.Render()
  if not frame or not ns.UI.Shown("wanted") then return end
  local lines = WantedUI.Lines()
  for i, l in ipairs(lines) do
    local r = row(i)
    r.text:SetText(l.text)
    r.entry = l.entry
    r:Show()
  end
  for i = #lines + 1, #rows do
    rows[i]:Hide()
    rows[i].entry = nil
  end
  frame.content:SetSize(WIDTH, math.max(#lines, 1) * ROW)
  if #lines == 0 then frame.empty:Show() else frame.empty:Hide() end
end

--- Rafraîchissement regroupé (une mort peut en suivre une autre).
function WantedUI.Refresh()
  if not frame or not ns.UI.Shown("wanted") or pending then return end
  pending = true
  C_Timer.After(ns.Data.ROSTER_REFRESH, function()
    pending = false
    ns.Safe("wanted.render", WantedUI.Render)
  end)
end

local function build(panel)
  frame = panel
  frame.hint = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  frame.hint:SetPoint("TOPLEFT", 16, -46)
  frame.hint:SetWidth(520)
  frame.hint:SetJustifyH("LEFT")
  frame.hint:SetText(L.WANTED_HINT)
  frame.scroll = CreateFrame("ScrollFrame", nil, frame, "UIPanelScrollFrameTemplate")
  frame.scroll:SetPoint("TOPLEFT", 16, -72)
  frame.scroll:SetPoint("BOTTOMRIGHT", -36, 40)
  frame.content = CreateFrame("Frame", nil, frame.scroll)
  frame.content:SetSize(WIDTH, ROW)
  frame.scroll:SetScrollChild(frame.content)
  frame.empty = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  frame.empty:SetPoint("TOPLEFT", 20, -78)
  frame.empty:SetWidth(500)
  frame.empty:SetJustifyH("LEFT")
  frame.empty:SetText(L.WANTED_EMPTY)
  frame.alerts = ns.UI.MakeCheck(frame, L.WANTED_ALERTS,
    function() return ns.db.settings.wantedAlerts end,
    function(on) ns.Wanted.SetAlerts(on) end)
  frame.alerts:SetPoint("BOTTOMLEFT", 12, 10)
end

ns.UI.AddTab({
  key = "wanted", order = 2, label = L.WANTED_BUTTON, name = "WoWForeverGuildeWanted", build = build,
  show = function() ns.Safe("wanted.render", WantedUI.Render) end,
})

function WantedUI.Toggle()
  ns.UI.Toggle("wanted")
end

function WantedUI.Frame() return frame end -- tests
