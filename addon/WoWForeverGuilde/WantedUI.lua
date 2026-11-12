-- Onglet « Wanted » de la fenêtre /mf (/mf wanted) : les têtes mises à prix, prime décroissante. Une ligne par
-- ennemi : nom coloré par classe, classe, prime, kills de la guilde (lot 2), dernière victime, lieu et âge ; survol :
-- la même infobulle que la tête de mort sur la carte.
local ADDON, ns = ...

local WantedUI = {}
ns.WantedUI = WantedUI
local L = ns.L

local COLUMNS = {
  { L.COL_WANTED, 0, 176 }, { L.COL_CLASS, 180, 74 }, { L.COL_PRIME, 258, 62 }, { L.COL_KILLED, 324, 50 },
  { L.COL_LAST, 378, 186 }, { L.COL_WHEN, 568, 80, "RIGHT" },
}
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

--- Les cellules d'un ennemi : nom, classe, prime, kills de la guilde, dernier fait connu et son âge.
local function cells(entry)
  local last, what, when = entry.last, "", ""
  if last then
    local place = ns.Wanted.Where(entry)
    place = place ~= "" and place or L.WHERE_UNKNOWN
    when = "|cffbcbcbc" .. ns.UI.Ago(last.t) .. "|r"
    if last.kind == "kill" then
      what = "|cff9ad19a" .. string.format(L.WANTED_CELL_KILL, ns.ClassColored(last.by or "?", last.byClass), place) .. "|r"
    elseif last.kind == "seen" then
      what = "|cffbcbcbc" .. string.format(L.WANTED_CELL_SEEN, place) .. "|r"
    else
      what = "|cffbcbcbc" .. string.format(L.WANTED_CELL_VICTIM, ns.ClassColored(last.victim or "?", last.victimClass), place) .. "|r"
    end
  end
  return {
    L.ICON_SKULL .. " " .. ns.ClassColored(entry.name, entry.class),
    "|cff9a9a9a" .. ns.ClassLabel(entry.class) .. "|r",
    "|cffffd100" .. ns.Points(entry.points) .. "|r",
    (entry.kills or 0) > 0 and ("|cff9accff" .. string.format(L.WANTED_CELL_KILLS, entry.kills) .. "|r") or "",
    what,
    when,
  }
end

local function row(i)
  local r = rows[i]
  if not r then
    r = ns.UI.MakeRow(frame.content, COLUMNS, i)
    r:SetScript("OnEnter", function(self) if self.entry then ns.MapUI.ShowWantedTooltip(self.entry, self) end end)
    r:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    rows[i] = r
  end
  return r
end

--- Lignes à afficher : { text, entry, cells }, prime décroissante. Exposé pour les tests.
function WantedUI.Lines()
  local list = ns.Wanted.Sorted()
  local lines = {}
  if #list == 0 then return lines end
  lines[#lines + 1] = { text = "|cffffd100" .. L.WANTED_SECTION .. "|r |cff9a9a9a(" .. #list .. ")|r" }
  for _, entry in ipairs(list) do lines[#lines + 1] = { text = line(entry), entry = entry, cells = cells(entry) } end
  return lines
end

function WantedUI.Render()
  if not frame or not ns.UI.Shown("wanted") then return end
  local lines = WantedUI.Lines()
  for i, l in ipairs(lines) do
    local r = row(i)
    ns.UI.FillRow(r, l)
    r.entry = l.entry
    r:Show()
  end
  for i = #lines + 1, #rows do
    rows[i]:Hide()
    rows[i].entry = nil
  end
  frame.content:SetSize(ns.UI.LIST_WIDTH, math.max(#lines, 1) * ns.UI.ROW_HEIGHT)
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
  frame.hint:SetWidth(ns.UI.LIST_WIDTH)
  frame.hint:SetJustifyH("LEFT")
  frame.hint:SetText(L.WANTED_HINT)
  frame.scroll = CreateFrame("ScrollFrame", nil, frame, "UIPanelScrollFrameTemplate")
  ns.UI.MakeColumnHeaders(frame, COLUMNS, -70)
  frame.scroll:SetPoint("TOPLEFT", 16, -88)
  frame.scroll:SetPoint("BOTTOMRIGHT", -36, 16)
  frame.content = CreateFrame("Frame", nil, frame.scroll)
  frame.content:SetSize(ns.UI.LIST_WIDTH, ns.UI.ROW_HEIGHT)
  frame.scroll:SetScrollChild(frame.content)
  frame.empty = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  frame.empty:SetPoint("TOPLEFT", 20, -94)
  frame.empty:SetWidth(500)
  frame.empty:SetJustifyH("LEFT")
  frame.empty:SetText(L.WANTED_EMPTY)
end

ns.UI.AddTab({
  key = "wanted", order = 2, label = L.WANTED_BUTTON, name = "WoWForeverGuildeWanted", build = build,
  show = function() ns.Safe("wanted.render", WantedUI.Render) end,
})

function WantedUI.Toggle()
  ns.UI.Toggle("wanted")
end

function WantedUI.Frame() return frame end -- tests
