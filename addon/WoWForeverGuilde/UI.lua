-- Interface : la fenêtre /mf et ses onglets (ici Collecte et Export ; Guilde et Wanted ont leur fichier),
-- dialogues (transfert, sauvegarde), texte flottant des morts. Sobre : rien ne s'ouvre tout seul hors dialogues.
local ADDON, ns = ...

local UI = {}
ns.UI = UI
local L = ns.L

function UI.Ago(ts)
  if not ts then return "?" end
  local delta = ns.now() - ts
  if delta < 60 then return L.JUST_NOW end
  if delta < 3600 then return string.format(L.MINUTES_AGO, math.floor(delta / 60)) end
  if delta < 48 * 3600 then return string.format(L.HOURS_AGO, math.floor(delta / 3600)) end
  return string.format(L.DAYS_AGO, math.floor(delta / 86400))
end

local function duration(seconds)
  local h = math.floor(seconds / 3600)
  local m = math.floor((seconds % 3600) / 60)
  if h > 0 then return string.format("%d h %02d", h, m) end
  return string.format("%d min", m)
end

local function dateText(ts)
  return ts and date("%d/%m/%Y", ts) or "?"
end

-- --- helpers de construction -------------------------------------------------------------------

local function makeFrame(name, width, height, title)
  local f = CreateFrame("Frame", name, UIParent, "BackdropTemplate")
  f:SetSize(width, height)
  f:SetPoint("CENTER")
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", f.StopMovingOrSizing)
  f:SetFrameStrata("DIALOG")
  if f.SetBackdrop then
    f:SetBackdrop({
      bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark",
      edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border", edgeSize = 24,
      insets = { left = 6, right = 6, top = 6, bottom = 6 },
    })
  end
  f.icon = f:CreateTexture(nil, "ARTWORK")
  f.icon:SetSize(26, 26)
  f.icon:SetPoint("TOPLEFT", 14, -10)
  f.icon:SetTexture(ns.Data.ICON)
  f.title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  f.title:SetPoint("LEFT", f.icon, "RIGHT", 8, 0)
  f.title:SetText(title)
  local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
  close:SetPoint("TOPRIGHT", -4, -4)
  f:Hide()
  tinsert(UISpecialFrames, name) -- Échap ferme
  return f
end

local function makeButton(parent, text, width)
  local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
  b:SetSize(width or 160, 24)
  b:SetText(text)
  return b
end
UI.MakeButton = makeButton

local function makeCheck(parent, label, get, set)
  local c = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
  c:SetSize(24, 24)
  c.text = c:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  c.text:SetPoint("LEFT", c, "RIGHT", 2, 0)
  c.text:SetText(label)
  c:SetScript("OnShow", function(self) self:SetChecked(get()) end)
  c:SetScript("OnClick", function(self) set(self:GetChecked() and true or false) end)
  return c
end
UI.MakeCheck = makeCheck

-- --- fenêtre à onglets ---------------------------------------------------------------------------
--
-- Une seule fenêtre (/mf), un onglet par écran. Chaque fichier d'interface déclare le sien avec UI.AddTab ; le
-- panneau n'est construit qu'à sa première ouverture. La position de la fenêtre et le dernier onglet ouvert sont
-- retenus d'une session à l'autre (réglages du compte).

local WINDOW_WIDTH, WINDOW_HEIGHT = 700, 512
-- Les panneaux commencent sous la rangée d'onglets : leur contenu garde les décalages des anciennes fenêtres, qui
-- laissaient 44 px à leur propre barre de titre.
local PANEL_TOP = 30
local WHITE = "Interface\\Buttons\\WHITE8X8"

local window, current
local tabs, tabOrder = {}, {}

--- Déclare un onglet : { key, order, label, name (nom global du panneau), build(panel), show(panel) }.
--- `show` est appelé à chaque fois que l'onglet devient visible (ouverture de la fenêtre, changement d'onglet).
function UI.AddTab(def)
  tabs[def.key] = def
  tabOrder[#tabOrder + 1] = def.key
  table.sort(tabOrder, function(a, b) return (tabs[a].order or 99) < (tabs[b].order or 99) end)
end

--- Cet onglet est-il à l'écran ?
function UI.Shown(key)
  return window ~= nil and window:IsShown() and current == key
end

local function paintTabs()
  for _, key in ipairs(tabOrder) do
    local button = tabs[key].button
    if button then
      local on = key == current
      if on then button.text:SetTextColor(1, 0.82, 0) else button.text:SetTextColor(0.7, 0.7, 0.7) end
      if on then button.line:Show() else button.line:Hide() end
    end
  end
end

local function selectTab(key)
  if not tabs[key] then key = tabOrder[1] end
  local def = tabs[key]
  if not def then return end
  current = key
  for _, other in ipairs(tabOrder) do
    local panel = tabs[other].panel
    if panel and other ~= key then panel:Hide() end
  end
  if not def.panel then
    def.panel = CreateFrame("Frame", def.name, window)
    def.panel:SetPoint("TOPLEFT", 0, -PANEL_TOP)
    def.panel:SetPoint("BOTTOMRIGHT", 0, 0)
    def.build(def.panel)
  end
  def.panel:Show()
  paintTabs()
  if ns.db then ns.db.settings.windowTab = key end
  if def.show then ns.Safe("ui." .. key, def.show, def.panel) end
end

local function buildWindow()
  window = makeFrame("WoWForeverGuildeFrame", WINDOW_WIDTH, WINDOW_HEIGHT, L.TITLE)
  window:SetClampedToScreen(true)
  window.version = window:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  window.version:SetPoint("LEFT", window.title, "RIGHT", 10, 0)
  window.version:SetText("v" .. tostring(ns.VERSION))
  local saved = ns.db and ns.db.settings.windowPoint
  if type(saved) == "table" and saved[1] then
    window:ClearAllPoints()
    window:SetPoint(saved[1], UIParent, saved[2] or saved[1], saved[3] or 0, saved[4] or 0)
  end
  window:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local point, _, relative, x, y = self:GetPoint(1)
    if point and ns.db then ns.db.settings.windowPoint = { point, relative, x, y } end
  end)

  local x = 14
  for _, key in ipairs(tabOrder) do
    local def = tabs[key]
    local button = CreateFrame("Button", nil, window)
    button.text = button:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    button.text:SetPoint("CENTER", 0, 1)
    button.text:SetText(def.label)
    local width = math.floor((button.text.GetStringWidth and button.text:GetStringWidth() or #def.label * 7) + 0.5) + 24
    button:SetSize(width, 24)
    button:SetPoint("TOPLEFT", x, -42)
    button.line = button:CreateTexture(nil, "ARTWORK")
    button.line:SetTexture(WHITE)
    button.line:SetVertexColor(1, 0.82, 0, 1)
    button.line:SetHeight(2)
    button.line:SetPoint("BOTTOMLEFT", 6, 0)
    button.line:SetPoint("BOTTOMRIGHT", -6, 0)
    button:SetScript("OnClick", function() selectTab(key) end)
    button:SetScript("OnEnter", function(self) self.text:SetTextColor(1, 1, 1) end)
    button:SetScript("OnLeave", paintTabs)
    def.button = button
    x = x + width + 4
  end
  window.tabRule = window:CreateTexture(nil, "ARTWORK")
  window.tabRule:SetTexture(WHITE)
  window.tabRule:SetVertexColor(1, 1, 1, 0.15)
  window.tabRule:SetHeight(1)
  window.tabRule:SetPoint("TOPLEFT", 12, -66)
  window.tabRule:SetPoint("TOPRIGHT", -12, -66)
end

--- Ouvre la fenêtre sur un onglet : celui demandé, sinon le dernier ouvert, sinon le premier.
function UI.Open(key)
  if not window then buildWindow() end
  window:Show()
  selectTab(key or current or (ns.db and ns.db.settings.windowTab) or tabOrder[1])
end

--- /mf et ses variantes : ouvre la fenêtre (sur l'onglet demandé), ou la ferme si elle y est déjà.
function UI.Toggle(key)
  if window and window:IsShown() and (not key or key == current) then
    window:Hide()
    return
  end
  UI.Open(key)
end

-- --- onglet Collecte : personnages du compte, réglages, état de la collecte ---------------------------

local main
local STATUS_ORDER = { "identity", "talents", "professions", "reputation", "pvp", "pve", "gathering", "wanted" }
local STATUS_LABEL = {
  identity = L.STATUS_IDENTITY, talents = L.STATUS_TALENTS, professions = L.STATUS_PROFESSIONS,
  reputation = L.STATUS_REPUTATION, pvp = L.STATUS_PVP, pve = L.STATUS_PVE, gathering = L.STATUS_GATHERING,
  wanted = L.STATUS_WANTED,
}

local function collector(name)
  for _, def in ipairs(ns.collectors) do if def.name == name then return def end end
end

local function defaultStatus(char, name)
  local at = char[name .. "_at"] or char[name .. "s_at"]
  return at and string.format(L.UP_TO_DATE, UI.Ago(at)) or L.NEVER_READ
end

local function buildCollect(panel)
  main = panel

  -- Colonne personnages
  main.charHeader = main:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  main.charHeader:SetPoint("TOPLEFT", 16, -44)
  main.charHeader:SetText(L.CHARACTERS)
  main.charLines = {}
  for i = 1, 10 do
    local line = main:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    line:SetPoint("TOPLEFT", 16, -62 - (i - 1) * 16)
    line:SetWidth(200)
    line:SetJustifyH("LEFT")
    main.charLines[i] = line
  end
  main.sendCheck = makeCheck(main, L.SEND_CHARACTER,
    function() return ns.char and not ns.Store.IsExcluded(ns.char.guid) end,
    function(on) if ns.char then ns.db.settings.excluded[ns.char.guid] = (not on) and true or nil end UI.Refresh() end)
  main.sendCheck:SetPoint("BOTTOMLEFT", 12, 228)
  main.positionCheck = makeCheck(main, L.SHARE_POSITION,
    function() return ns.db.settings.sharePosition end,
    function(on) ns.Positions.SetSharing(on) end)
  main.positionCheck:SetPoint("BOTTOMLEFT", 12, 206)
  main.minimapCheck = makeCheck(main, L.SHARE_MINIMAP,
    function() return ns.db.settings.minimapDots end,
    function(on) ns.MapUI.SetMinimap(on) end)
  main.minimapCheck:SetPoint("BOTTOMLEFT", 12, 184)
  main.gankCheck = makeCheck(main, L.GANK_ALERTS,
    function() return ns.db.settings.gankAlerts end,
    function(on) ns.db.settings.gankAlerts = on end)
  main.gankCheck:SetPoint("BOTTOMLEFT", 12, 162)
  main.playCheck = makeCheck(main, L.SHARE_PLAYTIME,
    function() return ns.db.settings.sharePlaytime end,
    function(on) ns.db.settings.sharePlaytime = on end)
  main.playCheck:SetPoint("BOTTOMLEFT", 12, 140)
  main.showDeaths = makeCheck(main, L.SHOW_DEATHS,
    function() return ns.db.settings.showDeaths end,
    function(on) ns.db.settings.showDeaths = on end)
  main.showDeaths:SetPoint("BOTTOMLEFT", 12, 118)
  main.soundDeaths = makeCheck(main, L.SOUND_DEATHS,
    function() return ns.db.settings.soundDeaths end,
    function(on) ns.db.settings.soundDeaths = on end)
  main.soundDeaths:SetPoint("BOTTOMLEFT", 12, 96)
  main.announceDeaths = makeCheck(main, L.ANNOUNCE_DEATHS,
    function() return ns.db.settings.announceDeaths end,
    function(on) ns.db.settings.announceDeaths = on end)
  main.announceDeaths:SetPoint("BOTTOMLEFT", 12, 74)
  main.wantedCheck = makeCheck(main, L.WANTED_ALERTS,
    function() return ns.db.settings.wantedAlerts end,
    function(on) ns.Wanted.SetAlerts(on) end)
  main.wantedCheck:SetPoint("BOTTOMLEFT", 12, 52)

  -- Colonne état
  main.statusHeader = main:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  main.statusHeader:SetPoint("TOPLEFT", 240, -44)
  main.since = main:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  main.since:SetPoint("TOPRIGHT", -16, -44)
  main.statusLines = {}
  local y = -64
  for _, name in ipairs(STATUS_ORDER) do
    local label = main:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    label:SetPoint("TOPLEFT", 240, y)
    label:SetText(STATUS_LABEL[name])
    local value = main:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    value:SetPoint("TOPRIGHT", -16, y)
    value:SetWidth(260)
    value:SetJustifyH("RIGHT")
    main.statusLines[name] = value
    y = y - (name == "professions" and 44 or 22)
  end

  -- Pied
  main.lastWrite = main:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  main.lastWrite:SetPoint("BOTTOMLEFT", 240, 74)
  main.session = main:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  main.session:SetPoint("BOTTOMRIGHT", -16, 74)
  -- Les onglets remplacent les boutons qui ouvraient les autres fenêtres : restent les deux actions.
  main.sosButton = makeButton(main, L.SOS_BUTTON, 118)
  main.sosButton:SetPoint("BOTTOMLEFT", 12, 12)
  main.sosButton:SetScript("OnClick", function() ns.Positions.SOS() end)
  main.saveButton = makeButton(main, L.SAVE_NOW, 170)
  main.saveButton:SetPoint("LEFT", main.sosButton, "RIGHT", 8, 0)
  main.saveButton:SetScript("OnClick", function() ReloadUI() end)
  main.hint = main:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  main.hint:SetPoint("BOTTOMRIGHT", -16, 44)
  main.hint:SetText(L.REOPEN)
end

function UI.Refresh()
  if not main or not UI.Shown("collect") then return end
  local db, char = ns.db, ns.char
  local guids = {}
  for guid, entry in pairs(db.characters) do if entry.name then guids[#guids + 1] = guid end end
  table.sort(guids, function(a, b) return (db.characters[a].updated_at or 0) > (db.characters[b].updated_at or 0) end)
  for i, line in ipairs(main.charLines) do
    local guid = guids[i]
    if guid then
      local e = db.characters[guid]
      local color = (RAID_CLASS_COLORS and e.class and RAID_CLASS_COLORS[e.class]) or nil
      local name = color and ("|c" .. (color.colorStr or "ffffffff") .. e.name .. "|r") or e.name
      local suffix = guid == (char and char.guid) and " · connecté" or (" · " .. UI.Ago(e.updated_at))
      if db.settings.excluded[guid] then suffix = " · |cff9a9a9aexclu du site|r" end
      line:SetText(string.format("%s |cff9a9a9a%s %d|r%s", name, e.class or "?", e.level or 0, suffix))
      line:Show()
    else
      line:Hide()
    end
  end
  if char then
    main.statusHeader:SetText(string.format(L.COLLECT, char.name or "?"))
    main.since:SetText(string.format(L.COUNTING_SINCE, dateText(char.counting_since)))
    for _, name in ipairs(STATUS_ORDER) do
      local def = collector(name)
      local text = def and def.status and select(2, ns.Safe(name .. ".status", def.status, char)) or nil
      if type(text) ~= "string" then text = defaultStatus(char, name) end
      main.statusLines[name]:SetText(text)
    end
  end
  main.lastWrite:SetText(db.last_write and string.format(L.LAST_WRITE, UI.Ago(db.last_write)) or L.LAST_WRITE_NEVER)
  local unsaved = ns.now() - (ns.lastWrite or ns.sessionStart or ns.now())
  main.session:SetText(string.format(L.SESSION_UNSAVED, duration(unsaved)))
  main.session:SetTextColor(unsaved >= ns.Data.RELOAD_REMINDER_SECONDS and 1 or 0.6, unsaved >= ns.Data.RELOAD_REMINDER_SECONDS and 0.72 or 0.6, 0.29)
end

UI.AddTab({ key = "collect", order = 3, label = L.TAB_COLLECT, name = "WoWForeverGuildeCollect", build = buildCollect, show = UI.Refresh })

-- --- onglet Export : le code à coller sur le site, sans compagnon ---------------------------------------

local exportFrame
local fillExport

local function buildExport(panel)
  exportFrame = panel
  local steps = exportFrame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  steps:SetPoint("TOPLEFT", 16, -44)
  steps:SetWidth(520)
  steps:SetJustifyH("LEFT")
  steps:SetText(L.EXPORT_STEP1 .. "\n" .. L.EXPORT_STEP2 .. "\n|cff9a9a9a" .. L.EXPORT_STEP3 .. "|r")
  exportFrame.meta = exportFrame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  exportFrame.meta:SetPoint("TOPLEFT", 16, -104)

  local scroll = CreateFrame("ScrollFrame", nil, exportFrame, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 16, -120)
  scroll:SetPoint("BOTTOMRIGHT", -36, 80)
  local box = CreateFrame("EditBox", nil, scroll)
  box:SetMultiLine(true)
  box:SetAutoFocus(false)
  box:SetFontObject(ChatFontSmall or GameFontHighlightSmall)
  box:SetWidth(WINDOW_WIDTH - 60)
  box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  box:SetScript("OnTextChanged", function(self, user)
    if user and exportFrame.code and self:GetText() ~= exportFrame.code then self:SetText(exportFrame.code) end
  end)
  scroll:SetScrollChild(box)
  exportFrame.box = box

  exportFrame.content = exportFrame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  exportFrame.content:SetPoint("BOTTOMLEFT", 16, 56)
  exportFrame.content:SetWidth(520)
  exportFrame.content:SetJustifyH("LEFT")
  local selectAll = makeButton(exportFrame, L.SELECT_ALL, 150)
  selectAll:SetPoint("BOTTOMLEFT", 16, 20)
  selectAll:SetScript("OnClick", function() box:SetFocus() box:HighlightText() end)
  local regen = makeButton(exportFrame, L.REGENERATE, 120)
  regen:SetPoint("LEFT", selectAll, "RIGHT", 8, 0)
  regen:SetScript("OnClick", function() fillExport() end)
  local warn = exportFrame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  warn:SetPoint("BOTTOMRIGHT", -16, 26)
  warn:SetText(L.TRUNCATED_WARNING)
end

--- Relit le personnage et régénère le code, sélectionné et prêt à copier : à chaque ouverture de l'onglet.
function fillExport()
  local char = ns.char
  if char then
    for _, def in ipairs(ns.collectors) do
      if def.scan then ns.Safe(def.name .. ".scan", def.scan, char) end
    end
    char.updated_at = ns.now()
  end
  local ok, code = ns.Safe("Export.Build", ns.Export.Build, ns.now())
  if not ok then ns.Print("Export impossible : " .. tostring(code)) return end
  exportFrame.code = code
  exportFrame.box:SetText(code)
  exportFrame.meta:SetText(string.format(L.EXPORT_META, string.format("%.1f Ko", #code / 1024)))
  local included, excluded = ns.Export.Describe(ns.db)
  local text = string.format(L.EXPORT_CONTENT, table.concat(included, ", "))
  if #excluded > 0 then text = text .. "  |cff9a9a9a(exclus : " .. table.concat(excluded, ", ") .. ")|r" end
  exportFrame.content:SetText(text)
  exportFrame.box:SetFocus()
  exportFrame.box:HighlightText()
end

UI.AddTab({ key = "export", order = 4, label = L.TAB_EXPORT, name = "WoWForeverGuildeExport", build = buildExport, show = fillExport })

--- /mf export : ouvre la fenêtre sur le code d'export.
function UI.ShowExport()
  UI.Open("export")
end

-- --- dialogues ---------------------------------------------------------------------------------------

StaticPopupDialogs["WFG_TRANSFER"] = {
  text = "%s",
  button1 = L.TRANSFER_YES,
  button2 = L.TRANSFER_NO,
  OnAccept = function(self, data)
    ns.Store.Merge(data.entry, data.candidate)
    ns.Print(L.TRANSFER_DONE)
  end,
  timeout = 0, whileDead = true, hideOnEscape = false, preferredIndex = 3,
}

function UI.AskTransfer(entry, candidate)
  local class = ns.ClassLabel(candidate.class) -- le nom de la classe (« Chaman »), pas son jeton (« SHAMAN »)
  local text = string.format(L.TRANSFER_TEXT, UnitName("player") or "?", candidate.name or "?", class ~= "" and class or "?", candidate.level or 0)
  local dialog = StaticPopup_Show("WFG_TRANSFER", text)
  if dialog then dialog.data = { entry = entry, candidate = candidate } end
end

StaticPopupDialogs["WFG_RELOAD"] = {
  text = "%s",
  button1 = L.RELOAD_YES,
  button2 = L.RELOAD_LATER,
  button3 = L.RELOAD_NEVER,
  OnAccept = function() ReloadUI() end,
  OnAlt = function() ns.db.settings.reloadReminder = false end,
  timeout = 0, whileDead = true, hideOnEscape = true, preferredIndex = 3,
}

function UI.SuggestReload(unsaved)
  StaticPopup_Show("WFG_RELOAD", string.format(L.RELOAD_TEXT, duration(unsaved)))
end

StaticPopupDialogs["WFG_UPGRADE"] = {
  text = "%s",
  button1 = L.UPGRADE_YES,
  button2 = L.UPGRADE_LATER,
  OnAccept = function() ReloadUI() end,
  timeout = 0, whileDead = true, hideOnEscape = true, preferredIndex = 3,
}

--- Un guildien a une version plus récente de l'addon : proposer le /reload (le compagnon a déjà copié les fichiers).
function UI.SuggestUpgrade(version)
  StaticPopup_Show("WFG_UPGRADE", string.format(L.UPGRADE_TEXT, version, tostring(ns.VERSION)))
end

function UI.OnLogin(entry)
  ns.Print(L.WELCOME, entry.name or UnitName("player") or "", dateText(entry.counting_since))
  local recent = 0
  for _, e in ipairs((ns.db and ns.db.errors) or {}) do
    if (e.t or 0) >= ns.now() - 86400 then recent = recent + 1 end
  end
  if recent > 0 then ns.Print(L.ERRORS_RECENT, recent) end
end

-- --- texte flottant des morts ---------------------------------------------------------------------------

local toast

local function buildToast()
  toast = CreateFrame("Frame", "WoWForeverGuildeDeath", UIParent)
  toast:SetSize(900, 140)
  toast:SetPoint("TOP", 0, -96)
  toast:SetFrameStrata("HIGH")
  toast:EnableMouse(false)
  toast.header = toast:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  toast.header:SetPoint("TOP", 0, 0)
  toast.header:SetTextColor(0.79, 0.79, 0.79)
  toast.header:SetText(L.DEATH_HEADER)
  toast.text = toast:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge")
  toast.text:SetPoint("TOP", toast.header, "BOTTOM", 0, -8)
  toast.text:SetWidth(900)
  toast.text:SetJustifyH("CENTER")
  toast.text:SetTextColor(1, 0.35, 0.24)
  toast.text:SetShadowOffset(2, -2)
  toast.footer = toast:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  toast.footer:SetPoint("TOP", toast.text, "BOTTOM", 0, -8)
  toast.footer:SetTextColor(0.9, 0.85, 0.72)
  toast:Hide()
end

--- Texte flottant TOAST_SECONDS s : en-tête, phrase colorée, pied, et son d'avertissement si demandé.
--- Un texte encore à l'écran depuis moins de TOAST_MIN_SECONDS s n'est pas écrasé : le suivant attend son tour
--- (0.6.8 ; deux kills à 2 s d'écart, et le premier popup n'était jamais lu). Exception : un texte de même `key`
--- que celui à l'écran le corrige sur place (la même mort annoncée PvE puis PvP : un seul avis).
--- `label` : ce que /mf api retient du popup (qui, quoi, où), la phrase étant tirée au hasard.
local waiting, shownAt, shownKey, nextTimer = {}, nil, nil, nil

-- /mf api : les derniers popups et ce qu'ils sont devenus (affiché, mis en attente, corrigé sur place, sorti de la
-- file, éjecté), pour comprendre en jeu un popup qui manque.
local toastLog = {}
local function logToast(what, label)
  label = tostring(label or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|T.-|t", "")
  toastLog[#toastLog + 1] = { t = ns.now(), what = what, label = label:sub(1, 60) }
  while #toastLog > 8 do table.remove(toastLog, 1) end
  ns.Trace("popup %s : %s", what, label)
end

function UI.ToastSource()
  if #toastLog == 0 then return "aucun popup cette session" end
  local parts = {}
  for i, e in ipairs(toastLog) do parts[i] = string.format("il y a %d s %s « %s »", ns.now() - e.t, e.what, e.label) end
  return table.concat(parts, " ; ") .. string.format(" · en attente : %d", #waiting)
end

local function display(headerText, text, footer, color, sound, key)
  shownAt, shownKey = ns.now(), key
  toast.header:SetText(headerText)
  toast.text:SetText(text)
  toast.text:SetTextColor(color[1], color[2], color[3])
  toast.footer:SetText(footer or "")
  if toast.timer then toast.timer:Cancel() end
  toast:SetAlpha(0)
  toast:Show()
  UIFrameFadeIn(toast, 0.3, 0, 1)
  if sound and PlaySound and SOUNDKIT and SOUNDKIT.RAID_WARNING then PlaySound(SOUNDKIT.RAID_WARNING, "Master") end
  local at = shownAt
  toast.timer = C_Timer.NewTimer(ns.Data.TOAST_SECONDS, function()
    UIFrameFadeOut(toast, 1, 1, 0)
    -- Un texte arrivé pendant le fondu ne doit pas être caché par la fin du précédent.
    C_Timer.After(1, function() if shownAt == at and toast.fading == at then toast:Hide() end end)
    toast.fading = at
  end)
  toast.fading = nil
end

local function showNext()
  nextTimer = nil
  local item = table.remove(waiting, 1)
  if not item then return end
  logToast("sorti de la file", item[7])
  display(item[1], item[2], item[3], item[4], item[5], item[6])
  if #waiting > 0 then nextTimer = C_Timer.NewTimer(ns.Data.TOAST_MIN_SECONDS, showNext) end
end

--- Ce texte est-il encore à l'écran ou en attente dans la file ?
function UI.ToastPending(key)
  if toast and toast:IsShown() and shownKey == key then return true end
  for _, item in ipairs(waiting) do
    if item[6] == key then return true end
  end
  return false
end

function UI.ShowToast(headerText, text, footer, color, sound, key, label)
  if not toast then buildToast() end
  label = label or footer
  local busy = toast:IsShown() and shownAt and ns.now() - shownAt < ns.Data.TOAST_MIN_SECONDS
  if (not busy and #waiting == 0) or (key and toast:IsShown() and key == shownKey) then
    logToast((busy or #waiting > 0) and "corrigé sur place" or "affiché", label)
    display(headerText, text, footer, color, sound, key)
    return
  end
  for i, item in ipairs(waiting) do
    if key and item[6] == key then -- encore en attente : corrigé à sa place dans la file
      waiting[i] = { headerText, text, footer, color, sound, key, label }
      logToast("corrigé dans la file", label)
      return
    end
  end
  waiting[#waiting + 1] = { headerText, text, footer, color, sound, key, label }
  logToast("mis en attente", label)
  while #waiting > ns.Data.TOAST_QUEUE do logToast("éjecté de la file", table.remove(waiting, 1)[7]) end
  if not nextTimer then
    nextTimer = C_Timer.NewTimer(math.max(0.1, ns.Data.TOAST_MIN_SECONDS - (ns.now() - (shownAt or 0))), showNext)
  end
end

--- Avis de décès. La phrase (ns.DeathPhrase) arrive prête, noms colorés ; le pied donne les faits : niveau, classe,
--- lieu, et pour une mort PvP la mention ou la prime. `wanted` : l'entrée du tueur dans le tableau Wanted quand
--- c'est un joueur recherché ; avec les alertes Wanted cochées, le pied porte sa prime (un seul cadre, pas deux).
function UI.ShowDeath(info, phrase, wanted)
  local parts = {}
  if (info.level or 0) > 0 then parts[#parts + 1] = string.format(L.DEATH_LEVEL, info.level) end
  local class = ns.ClassLabel(info.class)
  if class ~= "" then parts[#parts + 1] = class end
  local place = (info.zone and info.zone ~= "") and info.zone or (info.sub or "")
  if place ~= "" then parts[#parts + 1] = place end
  local header = L.DEATH_HEADER
  if wanted and ns.db.settings.wantedAlerts then
    header = L.DEATH_WANTED_HEADER
    parts[#parts + 1] = string.format(L.DEATH_WANTED, ns.Points(wanted.points), wanted.name or info.killer or "?")
  elseif info.player then
    -- Mort PvP : toujours dite « WANTED », même sans les alertes Wanted (alors sans la prime).
    header = L.DEATH_WANTED_HEADER
    parts[#parts + 1] = L.DEATH_PVP
  end
  local label = string.format(L.DEATH_LOG, tostring(info.name), info.killer or "")
  UI.ShowToast(header, phrase, table.concat(parts, " · "), { 1, 0.35, 0.24 }, ns.db.settings.soundDeaths,
    "mort:" .. tostring(info.name), label)
end

--- Appel à l'aide d'un membre dans ma zone : qui et par qui dans le texte, où dans le pied.
function UI.ShowAlert(peer, text)
  local place = ns.Positions.Where(peer)
  UI.ShowToast(L.ALERT_HEADER, text, place ~= "" and place or L.WHERE_UNKNOWN, { 1, 0.62, 0.2 }, true)
end

--- Victoire honorable : un joueur adverse abattu par un membre (moi ou un autre), hors champ de bataille. Vert,
--- sans son (il y en a bien plus que de morts). La phrase (Wanted.KillPhrase) arrive prête ; le pied dit où.
--- `hunters` : { { name, class }, … }, tous ceux du kill ; un chasseur de plus complète le popup sur place (même clé).
--- `id` : le kill, clé du popup ; `updateOnly` : ne corrige que s'il est encore à l'écran ou en attente.
function UI.ShowKill(victim, hunters, phrase, place, id, updateOnly)
  place = place ~= "" and place or L.WHERE_UNKNOWN
  local key = "kill:" .. tostring(id or victim)
  if updateOnly and not UI.ToastPending(key) then return end
  local label = string.format(#hunters > 1 and L.KILL_LOG_PLURAL or L.KILL_LOG, ns.Wanted.HunterNames(hunters), victim, place)
  UI.ShowToast(L.KILL_HEADER, phrase, place, { 0.45, 0.9, 0.45 }, false, key, label)
end

--- Prime encaissée : un recherché abattu par un membre (moi ou un autre). Or, son si les morts en ont un. La
--- phrase (Wanted.BountyPhrase) arrive prête ; le pied donne la prime et le lieu.
function UI.ShowBounty(entry, phrase, by, prime, place)
  place = place ~= "" and place or L.WHERE_UNKNOWN
  local label = string.format(L.BOUNTY_LOG, by, entry.name, ns.Points(prime), place)
  UI.ShowToast(L.BOUNTY_HEADER, phrase, string.format(L.BOUNTY_FOOTER, ns.Points(prime), place), { 1, 0.82, 0 },
    ns.db.settings.soundDeaths, nil, label)
end
