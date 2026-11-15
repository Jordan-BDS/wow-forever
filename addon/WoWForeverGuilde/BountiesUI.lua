-- Onglet « Primes » de la fenêtre /mf (/mf primes) : poser une prime sans taper de commande, et voir celles en
-- cours. En haut le formulaire : joueur adverse (ou guilde, case cochée), or par kill, kills payés au plus ;
-- « Ma cible » reprend le nom de la cible (ou de sa guilde). « Poser la prime » passe par la même confirmation que
-- `/mf prime`. En dessous les primes en cours, les plus fortes d'abord ; un clic sur l'une des miennes l'annule,
-- après confirmation.
--
-- Clic droit sur le portrait d'un joueur adverse (cible, focus) : « Ajouter une prime » ouvre cet onglet, le nom
-- rempli ; « Prime sur la guilde … » fait de même pour sa guilde. L'entrée passe par le menu du jeu
-- (`Menu.ModifyMenu`), ou par l'ancien (`UnitPopup_ShowMenu`) si le client n'a que celui-là.
local ADDON, ns = ...

local BountiesUI = {}
ns.BountiesUI = BountiesUI
local L = ns.L

local COLUMNS = {
  { L.BOUNTY_COL_TARGET, 0, 196 }, { L.BOUNTY_COL_REWARD, 200, 150 }, { L.BOUNTY_COL_BY, 354, 130 },
  { L.BOUNTY_COL_SEEN, 488, 100 }, { "", 592, 56, "RIGHT" },
}
local LIST_TOP = 196
local frame
local rows = {}
local pending = false

local function trim(s)
  return (tostring(s or ""):gsub("^%s+", ""):gsub("%s+$", ""))
end

local function cells(entry)
  local seen = ""
  if entry.seen and entry.seen.t then seen = "|cffbcbcbc" .. ns.UI.Ago(entry.seen.t) .. "|r" end
  local target = entry.kind == "g" and ns.Bounties.Label(entry) or ns.ClassColored(entry.name, entry.class)
  return {
    L.ICON_COIN .. " " .. target,
    "|cffffd100" .. ns.Bounties.Reward(entry) .. "|r",
    ns.ClassColored(entry.by or "?", entry.byClass),
    seen,
    ns.Bounties.IsMine(entry) and entry.guid and L.BOUNTY_ROW_CANCEL or "",
  }
end

--- Lignes à afficher : { entry, cells }, les primes les plus fortes d'abord. Exposé pour les tests.
function BountiesUI.Lines()
  local lines = {}
  for _, entry in ipairs(ns.Bounties.Sorted()) do lines[#lines + 1] = { entry = entry, cells = cells(entry) } end
  return lines
end

--- Clic sur une ligne : annuler ma prime, après confirmation.
local function askCancel(entry)
  if not (entry and ns.Bounties.Open(entry) and ns.Bounties.IsMine(entry) and entry.guid) then return end
  ns.UI.Dialogs.WFG_BOUNTY_CANCEL = ns.UI.Dialogs.WFG_BOUNTY_CANCEL or {
    button1 = L.BOUNTY_CANCEL_YES,
    button2 = L.BOUNTY_CANCEL_NO,
    OnAccept = function(_, data) ns.Bounties.CancelEntry(data.entry) end,
  }
  ns.UI.ShowDialog("WFG_BOUNTY_CANCEL", string.format(L.BOUNTY_CANCEL_ASK, ns.Bounties.Label(entry)), { entry = entry })
end

local function row(i)
  local r = rows[i]
  if not r then
    r = ns.UI.MakeRow(frame.content, COLUMNS, i)
    r:SetScript("OnClick", function(self) askCancel(self.entry) end)
    r:SetScript("OnEnter", function(self)
      if not (self.entry and GameTooltip) then return end
      ns.MapUI.ShowBountyTooltip(self.entry, self)
      if ns.Bounties.IsMine(self.entry) and self.entry.guid then
        GameTooltip:AddLine(L.BOUNTY_ROW_CANCEL_TIP, 1, 0.4, 0.4)
        GameTooltip:Show()
      end
    end)
    r:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    rows[i] = r
  end
  return r
end

function BountiesUI.Render()
  if not frame or not ns.UI.Shown("bounties") then return end
  local lines = BountiesUI.Lines()
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

--- Rafraîchissement regroupé (Bounties.lua l'appelle à chaque prime posée, annulée, vue ou payée d'un kill).
function BountiesUI.Refresh()
  if not frame or not ns.UI.Shown("bounties") or pending then return end
  pending = true
  C_Timer.After(ns.Data.ROSTER_REFRESH, function()
    pending = false
    ns.Safe("bounties.render", BountiesUI.Render)
  end)
end

local function say(text, bad)
  frame.status:SetText(text or "")
  frame.status:SetTextColor(bad and 1 or 0.6, bad and 0.4 or 0.9, bad and 0.4 or 0.6)
end

local function isGuild()
  return frame.guild:GetChecked() and true or false
end

--- « Ma cible » : le nom du joueur adverse ciblé, ou de sa guilde si la case est cochée.
local function fromTarget()
  local name, why = ns.Bounties.TargetName(isGuild())
  if not name then return say(why, true) end
  frame.name:SetText(name)
  say("")
end

--- « Poser la prime » : la même demande que `/mf prime`, confirmation comprise.
local function submit()
  local name = trim(frame.name:GetText())
  if name == "" then return say(L.BOUNTY_FORM_NO_NAME, true) end
  local gold, max = tonumber(trim(frame.gold:GetText())), tonumber(trim(frame.kills:GetText()))
  if trim(frame.kills:GetText()) == "" then max = 1 end
  local asked, why = ns.Bounties.Ask(name, gold, max or 0, isGuild() and "g" or nil)
  if not asked then return say(why, true) end
  say(L.BOUNTY_FORM_ASKED)
  frame.name:SetText("")
  frame.gold:SetText("")
  frame.kills:SetText("1")
end

local function label(parent, text, x, y)
  local s = parent:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  s:SetPoint("TOPLEFT", x, y)
  s:SetText(text)
  return s
end

local function input(parent, x, y, width, numeric, letters)
  local box = CreateFrame("EditBox", nil, parent, "InputBoxTemplate")
  box:SetSize(width, 20)
  box:SetPoint("TOPLEFT", x, y)
  box:SetAutoFocus(false)
  box:SetMaxLetters(letters)
  if numeric then box:SetNumeric(true) end
  box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  box:SetScript("OnEnterPressed", function(self)
    self:ClearFocus()
    ns.Safe("bounties.form", submit)
  end)
  return box
end

local function build(panel)
  frame = panel
  frame.hint = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  frame.hint:SetPoint("TOPLEFT", 16, -46)
  frame.hint:SetWidth(ns.UI.LIST_WIDTH)
  frame.hint:SetJustifyH("LEFT")
  frame.hint:SetText(L.BOUNTY_TAB_HINT)

  -- Le formulaire : une ligne de champs, la case « guilde » et les boutons dessous.
  frame.nameLabel = label(frame, L.BOUNTY_FORM_NAME, 16, -80)
  frame.name = input(frame, 22, -96, 220, false, 64)
  frame.target = ns.UI.MakeButton(frame, L.BOUNTY_FORM_TARGET, 90)
  frame.target:SetPoint("TOPLEFT", 250, -94)
  frame.target:SetScript("OnClick", function() ns.Safe("bounties.form", fromTarget) end)
  label(frame, L.BOUNTY_FORM_GOLD, 356, -80)
  frame.gold = input(frame, 362, -96, 80, true, 6)
  label(frame, L.BOUNTY_FORM_KILLS, 466, -80)
  frame.kills = input(frame, 472, -96, 60, true, 3)
  frame.kills:SetText("1")
  frame.name:SetScript("OnTabPressed", function() frame.gold:SetFocus() end)
  frame.gold:SetScript("OnTabPressed", function() frame.kills:SetFocus() end)
  frame.kills:SetScript("OnTabPressed", function() frame.name:SetFocus() end)

  frame.guild = ns.UI.MakeCheck(frame, L.BOUNTY_FORM_GUILD, function() return isGuild() end, function(on)
    frame.nameLabel:SetText(on and L.BOUNTY_FORM_GUILD_NAME or L.BOUNTY_FORM_NAME)
  end)
  frame.guild:SetPoint("TOPLEFT", 14, -124)
  frame.post = ns.UI.MakeButton(frame, L.BOUNTY_FORM_POST, 150)
  frame.post:SetPoint("TOPLEFT", 386, -124)
  frame.post:SetScript("OnClick", function() ns.Safe("bounties.form", submit) end)
  frame.status = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  frame.status:SetPoint("TOPLEFT", 16, -154)
  frame.status:SetWidth(ns.UI.LIST_WIDTH)
  frame.status:SetJustifyH("LEFT")

  -- Les primes en cours.
  ns.UI.MakeColumnHeaders(frame, COLUMNS, -(LIST_TOP - 18))
  frame.scroll = CreateFrame("ScrollFrame", nil, frame, "UIPanelScrollFrameTemplate")
  frame.scroll:SetPoint("TOPLEFT", 16, -LIST_TOP)
  frame.scroll:SetPoint("BOTTOMRIGHT", -36, 16)
  frame.content = CreateFrame("Frame", nil, frame.scroll)
  frame.content:SetSize(ns.UI.LIST_WIDTH, ns.UI.ROW_HEIGHT)
  frame.scroll:SetScrollChild(frame.content)
  frame.empty = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  frame.empty:SetPoint("TOPLEFT", 20, -(LIST_TOP + 6))
  frame.empty:SetText(L.BOUNTY_TAB_EMPTY)
end

ns.UI.AddTab({
  key = "bounties", order = 2.5, label = L.BOUNTY_TAB, name = "WoWForeverGuildeBounties", build = build,
  show = function() ns.Safe("bounties.render", BountiesUI.Render) end,
})

function BountiesUI.Frame() return frame end -- tests

--- Ouvre l'onglet, le formulaire rempli : ce nom (de joueur, ou de guilde si `guild`), un kill, l'or à saisir.
function BountiesUI.Prefill(name, guild)
  ns.UI.Open("bounties")
  if not frame then return end
  frame.guild:SetChecked(guild and true or false)
  frame.nameLabel:SetText(guild and L.BOUNTY_FORM_GUILD_NAME or L.BOUNTY_FORM_NAME)
  frame.name:SetText(name or "")
  frame.gold:SetText("")
  frame.kills:SetText("1")
  say(L.BOUNTY_FORM_PREFILLED)
  frame.gold:SetFocus()
end

-- --- clic droit sur un portrait --------------------------------------------------------------------------------

--- Ce que le menu de cette unité propose : le nom du joueur adverse et sa guilde ; nil si ce n'en est pas un ou
--- si son nom est illisible.
local function menuTarget(unit)
  if type(unit) ~= "string" then return nil end
  local okPlayer, player = pcall(UnitIsPlayer or function() end, unit)
  local okAttack, hostile = pcall(UnitCanAttack or function() end, "player", unit)
  if not (okPlayer and ns.plain(player) == true and okAttack and ns.plain(hostile) == true) then return nil end
  local name = ns.UnitDisplayName(unit)
  if not name then return nil end
  return name, ns.UnitGuild(unit)
end

--- Les entrées à ajouter au menu d'une unité : { { text, run }, … }, vide si rien à proposer. Exposé pour les tests.
function BountiesUI.MenuEntries(unit)
  local ok, name, guild = pcall(menuTarget, unit)
  if not ok or not name then return {} end
  local entries = {
    { text = L.BOUNTY_MENU_ADD, run = function() ns.Safe("bounties.menu", BountiesUI.Prefill, name, false) end },
  }
  if guild then
    entries[#entries + 1] = {
      text = string.format(L.BOUNTY_MENU_ADD_GUILD, guild),
      run = function() ns.Safe("bounties.menu", BountiesUI.Prefill, guild, true) end,
    }
  end
  return entries
end

if type(Menu) == "table" and type(Menu.ModifyMenu) == "function" then
  local function extend(_, root, context)
    local entries = BountiesUI.MenuEntries(type(context) == "table" and context.unit or nil)
    if #entries == 0 then return end
    if root.CreateDivider then root:CreateDivider() end
    for _, entry in ipairs(entries) do root:CreateButton(entry.text, entry.run) end
  end
  for _, tag in ipairs({ "MENU_UNIT_ENEMY_PLAYER", "MENU_UNIT_TARGET", "MENU_UNIT_FOCUS", "MENU_UNIT_PLAYER" }) do
    pcall(Menu.ModifyMenu, tag, function(...)
      local ok, err = pcall(extend, ...)
      if not ok and ns.Store then ns.Store.LogError("bounties.menu", err) end
    end)
  end
elseif type(UnitPopup_ShowMenu) == "function" and type(UIDropDownMenu_AddButton) == "function" then
  hooksecurefunc("UnitPopup_ShowMenu", function(_, _, unit)
    if (UIDROPDOWNMENU_MENU_LEVEL or 1) ~= 1 then return end
    for _, entry in ipairs(BountiesUI.MenuEntries(unit)) do
      UIDropDownMenu_AddButton({ text = entry.text, notCheckable = true, func = entry.run })
    end
  end)
end
