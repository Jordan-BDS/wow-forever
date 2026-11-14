-- Interface : la fenêtre /mf et ses onglets (ici Collecte, Réglages, Nouveautés et Diagnostic ; Guilde et
-- Wanted ont leur fichier. Pas de fichier par onglet pour les nouveaux : le client ne lit la liste des fichiers
-- qu'à son lancement, un onglet ajouté dans un fichier neuf manquerait après une mise à jour suivie d'un /reload),
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
  c.get = get
  c:SetScript("OnShow", function(self) self:SetChecked(get()) end)
  c:SetScript("OnClick", function(self) set(self:GetChecked() and true or false) end)
  return c
end
UI.MakeCheck = makeCheck

-- Listes en colonnes (Guilde en jeu, Wanted). Une colonne : { titre, x, largeur, alignement }.
UI.LIST_WIDTH = 648
UI.ROW_HEIGHT = 18

--- Les titres des colonnes, posés à `y` sous le haut du panneau, au-dessus de la zone qui défile.
function UI.MakeColumnHeaders(parent, columns, y)
  parent.columnHeaders = {}
  for i, column in ipairs(columns) do
    local header = parent:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    header:SetPoint("TOPLEFT", 16 + column[2], y)
    header:SetWidth(column[3])
    header:SetJustifyH(column[4] or "LEFT")
    header:SetText(column[1])
    parent.columnHeaders[i] = header
  end
end

--- Une ligne de liste : un texte sur toute la largeur (titre de groupe) et une cellule par colonne, coupée à
--- sa largeur plutôt que de déborder sur la suivante.
function UI.MakeRow(parent, columns, index)
  local row = CreateFrame("Button", nil, parent)
  row:SetSize(UI.LIST_WIDTH, UI.ROW_HEIGHT)
  row:SetPoint("TOPLEFT", 0, -(index - 1) * UI.ROW_HEIGHT)
  row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
  row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  row.text:SetPoint("LEFT", 0, 0)
  row.text:SetWidth(UI.LIST_WIDTH)
  row.text:SetJustifyH("LEFT")
  row.cells = {}
  for i, column in ipairs(columns) do
    local cell = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    cell:SetPoint("LEFT", column[2], 0)
    cell:SetWidth(column[3])
    cell:SetJustifyH(column[4] or "LEFT")
    cell:SetWordWrap(false)
    row.cells[i] = cell
  end
  return row
end

--- Remplit une ligne : `line.cells` (une valeur par colonne) ou, sans cellules, `line.text` sur toute la largeur.
function UI.FillRow(row, line)
  row.text:SetText(line.cells and "" or line.text)
  for i, cell in ipairs(row.cells) do cell:SetText(line.cells and line.cells[i] or "") end
end

-- --- fenêtre à onglets ---------------------------------------------------------------------------
--
-- Une seule fenêtre (/mf), un onglet par écran. Chaque fichier d'interface déclare le sien avec UI.AddTab ; le
-- panneau n'est construit qu'à sa première ouverture. La fenêtre s'ouvre sur le premier onglet (l'historique) ;
-- sa position est retenue d'une session à l'autre (réglages du compte).

local WINDOW_WIDTH, WINDOW_HEIGHT = 700, 512
-- Les panneaux commencent sous la rangée d'onglets : leur contenu garde les décalages des anciennes fenêtres, qui
-- laissaient 44 px à leur propre barre de titre.
local PANEL_TOP = 30
local WHITE = "Interface\\Buttons\\WHITE8X8"

local window, current
local tabs, tabOrder = {}, {}

--- Déclare un onglet : { key, order, label, name (nom global du panneau), build(panel), show(panel), badge() }.
--- `show` est appelé à chaque fois que l'onglet devient visible (ouverture de la fenêtre, changement d'onglet).
--- `badge` : vrai tant que l'onglet a du neuf à montrer, il est alors en vert.
function UI.AddTab(def)
  tabs[def.key] = def
  tabOrder[#tabOrder + 1] = def.key
  table.sort(tabOrder, function(a, b) return (tabs[a].order or 99) < (tabs[b].order or 99) end)
end

--- Cet onglet est-il à l'écran ?
function UI.Shown(key)
  return window ~= nil and window:IsShown() and current == key
end

--- En-tête, commun à tous les onglets : depuis quand la session n'est pas sauvegardée.
local function refreshHeader()
  if not window then return end
  local unsaved = ns.now() - (ns.lastWrite or ns.sessionStart or ns.now())
  local late = unsaved >= ns.Data.RELOAD_REMINDER_SECONDS
  window.session:SetText(string.format(L.SESSION_UNSAVED, duration(unsaved)))
  window.session:SetTextColor(late and 1 or 0.6, late and 0.72 or 0.6, 0.29)
end

local function paintTabs()
  for _, key in ipairs(tabOrder) do
    local button = tabs[key].button
    if button then
      local on = key == current
      local badge = not on and tabs[key].badge and tabs[key].badge()
      button.fresh = badge and true or false
      if on then
        button.text:SetTextColor(1, 0.82, 0)
      elseif badge then
        button.text:SetTextColor(0.35, 0.82, 0.35)
      else
        button.text:SetTextColor(0.7, 0.7, 0.7)
      end
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
  refreshHeader()
  if def.show then ns.Safe("ui." .. key, def.show, def.panel) end
end

local function buildWindow()
  window = makeFrame("WoWForeverGuildeFrame", WINDOW_WIDTH, WINDOW_HEIGHT, L.TITLE)
  window:SetClampedToScreen(true)
  window.version = window:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  window.version:SetPoint("LEFT", window.title, "RIGHT", 10, 0)
  window.version:SetText("v" .. tostring(ns.VERSION))
  -- Sauvegarde : à droite du titre, à portée depuis tous les onglets.
  window.save = makeButton(window, L.SAVE_NOW, 160)
  window.save:SetPoint("TOPRIGHT", -36, -10)
  window.save:SetScript("OnClick", function() ReloadUI() end)
  window.session = window:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  window.session:SetPoint("RIGHT", window.save, "LEFT", -10, 0)
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

--- Ouvre la fenêtre sur un onglet : celui demandé, sinon le premier (l'historique).
function UI.Open(key)
  if not window then buildWindow() end
  window:Show()
  selectTab(key or tabOrder[1])
end

--- /mf et ses variantes : ouvre la fenêtre (sur l'onglet demandé), ou la ferme si elle y est déjà.
function UI.Toggle(key)
  if window and window:IsShown() and (not key or key == current) then
    window:Hide()
    return
  end
  UI.Open(key)
end

-- --- onglet Historique : les derniers décès et victoires de la guilde ---------------------------------------
--
-- Premier onglet, celui sur lequel la fenêtre s'ouvre. Chaque avis de décès, victoire honorable ou prime
-- encaissée y est noté avec la phrase et le pied de son popup, que les popups soient affichés ou non
-- (`db.history`, niveau compte, HISTORY_MAX entrées). Le plus récent en haut. On n'y trouve que ce que cet
-- addon a reçu : rien de ce qui s'est passé jeu fermé.

local HISTORY_ROW = 34
local HISTORY_KIND = {
  death = { L.HISTORY_DEATH, 1, 0.35, 0.24 },
  kill = { L.HISTORY_KILL, 0.45, 0.9, 0.45 },
  bounty = { L.HISTORY_BOUNTY, 1, 0.82, 0 },
}
local historyKeys = {} -- clé de popup → son entrée, pour la session : un popup corrigé sur place corrige l'entrée
local historyPanel
local historyRows = {}

--- Lignes à afficher, la plus récente d'abord : { text, sub, kind, entry }. Exposé pour les tests.
function UI.HistoryLines()
  local history = (ns.db and ns.db.history) or {}
  local lines = {}
  for i = #history, 1, -1 do
    local entry = history[i]
    local kind = HISTORY_KIND[entry.kind] or HISTORY_KIND.death
    local sub = UI.Ago(entry.t) .. " · " .. kind[1]
    if entry.footer and entry.footer ~= "" then sub = sub .. " · " .. entry.footer end
    lines[#lines + 1] = { text = entry.text or "", sub = sub, kind = entry.kind, entry = entry }
  end
  return lines
end

local function historyRow(i)
  local row = historyRows[i]
  if not row then
    row = CreateFrame("Button", nil, historyPanel.content)
    row:SetSize(UI.LIST_WIDTH, HISTORY_ROW)
    row:SetPoint("TOPLEFT", 0, -(i - 1) * HISTORY_ROW)
    row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
    row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    row.text:SetPoint("TOPLEFT", 0, -3)
    row.text:SetWidth(UI.LIST_WIDTH)
    row.text:SetJustifyH("LEFT")
    row.text:SetWordWrap(false)
    row.sub = row:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    row.sub:SetPoint("TOPLEFT", 0, -18)
    row.sub:SetWidth(UI.LIST_WIDTH)
    row.sub:SetJustifyH("LEFT")
    row.sub:SetWordWrap(false)
    -- Une phrase trop longue pour la ligne se lit en entier au survol.
    row:SetScript("OnEnter", function(self)
      if not GameTooltip or not self.line then return end
      GameTooltip:SetOwner(self, "ANCHOR_CURSOR")
      GameTooltip:ClearLines()
      GameTooltip:AddLine(self.line.text, 1, 1, 1, true)
      GameTooltip:AddLine(self.line.sub, 0.7, 0.7, 0.7, true)
      GameTooltip:Show()
    end)
    row:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    historyRows[i] = row
  end
  return row
end

local function renderHistory()
  if not historyPanel or not UI.Shown("history") then return end
  local lines = UI.HistoryLines()
  for i, line in ipairs(lines) do
    local row = historyRow(i)
    local kind = HISTORY_KIND[line.kind] or HISTORY_KIND.death
    row.text:SetText(line.text)
    row.text:SetTextColor(kind[2], kind[3], kind[4])
    row.sub:SetText(line.sub)
    row.line = line
    row:Show()
  end
  for i = #lines + 1, #historyRows do
    historyRows[i]:Hide()
    historyRows[i].line = nil
  end
  historyPanel.content:SetSize(UI.LIST_WIDTH, math.max(#lines, 1) * HISTORY_ROW)
  if #lines == 0 then historyPanel.empty:Show() else historyPanel.empty:Hide() end
end

--- Note un décès, une victoire ou une prime dans l'historique. `key` : la clé de son popup ; le même popup
--- corrigé dans la minute (un chasseur de plus, un nom qui arrive, une mort PvE requalifiée en PvP) corrige son
--- entrée au lieu d'en ajouter une.
function UI.Remember(kind, key, text, footer)
  local db = ns.db
  if not db then return end
  db.history = db.history or {}
  local now = ns.now()
  local entry = key and historyKeys[key] or nil
  if entry and now - entry.t <= ns.Data.HISTORY_MERGE then
    entry.text, entry.footer = text, footer
  else
    entry = { t = now, kind = kind, text = text, footer = footer }
    table.insert(db.history, entry)
    while #db.history > ns.Data.HISTORY_MAX do table.remove(db.history, 1) end
    if key then historyKeys[key] = entry end
  end
  renderHistory()
end

local function buildHistory(panel)
  historyPanel = panel
  panel.scroll = CreateFrame("ScrollFrame", nil, panel, "UIPanelScrollFrameTemplate")
  panel.scroll:SetPoint("TOPLEFT", 16, -44)
  panel.scroll:SetPoint("BOTTOMRIGHT", -36, 16)
  panel.content = CreateFrame("Frame", nil, panel.scroll)
  panel.content:SetSize(UI.LIST_WIDTH, HISTORY_ROW)
  panel.scroll:SetScrollChild(panel.content)
  panel.empty = panel:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  panel.empty:SetPoint("TOPLEFT", 20, -50)
  panel.empty:SetWidth(UI.LIST_WIDTH)
  panel.empty:SetJustifyH("LEFT")
  panel.empty:SetText(L.HISTORY_EMPTY)
end

UI.AddTab({ key = "history", order = 0, label = L.TAB_HISTORY, name = "WoWForeverGuildeHistory", build = buildHistory, show = renderHistory })

-- --- onglet Collecte : personnages du compte, état de la collecte, export ------------------------------
--
-- Deux vues dans le même panneau : l'état (par défaut) et le code d'export, pour qui n'a pas le compagnon.

local main -- la vue « état »
local exportFrame -- la vue « export », construite à la première demande
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
  main = CreateFrame("Frame", nil, panel)
  main:SetAllPoints(panel)
  panel.status = main

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
  main.lastWrite:SetPoint("BOTTOMLEFT", 240, 44)
  main.exportButton = makeButton(main, L.EXPORT, 150)
  main.exportButton:SetPoint("BOTTOMLEFT", 12, 12)
  main.exportButton:SetScript("OnClick", function() UI.ShowExport() end)
  main.hint = main:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  main.hint:SetPoint("BOTTOMRIGHT", -16, 18)
  main.hint:SetText(L.REOPEN)
end

function UI.Refresh()
  if not main or not main:IsShown() or not UI.Shown("collect") then return end
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
end

--- L'onglet s'ouvre toujours sur l'état ; l'export se demande (bouton, /mf export).
local function showCollect()
  if exportFrame then exportFrame:Hide() end
  main:Show()
  UI.Refresh()
end

UI.AddTab({ key = "collect", order = 3, label = L.TAB_COLLECT, name = "WoWForeverGuildeCollect", build = buildCollect, show = showCollect })

local fillExport

local function buildExport(panel)
  exportFrame = CreateFrame("Frame", "WoWForeverGuildeExport", panel)
  exportFrame:SetAllPoints(panel)
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
  local back = makeButton(exportFrame, L.EXPORT_BACK, 150)
  back:SetPoint("BOTTOMLEFT", 12, 12)
  back:SetScript("OnClick", showCollect)
  local selectAll = makeButton(exportFrame, L.SELECT_ALL, 150)
  selectAll:SetPoint("LEFT", back, "RIGHT", 8, 0)
  selectAll:SetScript("OnClick", function() box:SetFocus() box:HighlightText() end)
  local regen = makeButton(exportFrame, L.REGENERATE, 120)
  regen:SetPoint("LEFT", selectAll, "RIGHT", 8, 0)
  regen:SetScript("OnClick", function() fillExport() end)
  local warn = exportFrame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  warn:SetPoint("BOTTOMRIGHT", -16, 18)
  warn:SetText(L.TRUNCATED_WARNING)
end

--- Relit le personnage et régénère le code, sélectionné et prêt à copier.
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

--- /mf export, bouton « Exporter le code » : l'onglet Collecte, sur le code d'export fraîchement généré.
function UI.ShowExport()
  UI.Open("collect")
  if not exportFrame then buildExport(tabs.collect.panel) end
  main:Hide()
  exportFrame:Show()
  fillExport()
end

-- --- onglet Réglages : toutes les cases, par sujet -------------------------------------------------------

local SETTINGS = {
  { L.SETTINGS_MAP, {
    { "sharePosition", L.SHARE_POSITION, function(on) ns.Positions.SetSharing(on) end },
    { "minimapDots", L.SHARE_MINIMAP, function(on) ns.MapUI.SetMinimap(on) end },
    { "minimapButton", L.MINIMAP_BUTTON, function(on) UI.SetMinimapButton(on) end },
    { "gankAlerts", L.GANK_ALERTS },
  } },
  { L.SETTINGS_DEATHS, {
    { "showDeaths", L.SHOW_DEATHS },
    { "soundDeaths", L.SOUND_DEATHS },
    { "announceDeaths", L.ANNOUNCE_DEATHS },
    { "wantedAlerts", L.WANTED_ALERTS, function(on) ns.Wanted.SetAlerts(on) end },
    -- NameplateUI.lua est un fichier neuf (0.7.4) : après une mise à jour suivie d'un /reload, le jeu ne l'a pas
    -- encore chargé (il ne relit la liste des fichiers qu'à son lancement). La case retient alors le choix seul.
    { "bountyPlates", L.BOUNTY_PLATES, function(on)
      if ns.Nameplates then ns.Nameplates.SetEnabled(on) else ns.db.settings.bountyPlates = on and true or false end
    end },
    { "showStreaks", L.SHOW_STREAKS },
    { "soundStreaks", L.SOUND_STREAKS },
  } },
  { L.SETTINGS_SITE, {
    -- Seul réglage propre au personnage connecté : les autres valent pour tout le compte.
    { "send", L.SEND_CHARACTER,
      function(on) if ns.char then ns.db.settings.excluded[ns.char.guid] = (not on) and true or nil end end,
      function() return ns.char ~= nil and not ns.Store.IsExcluded(ns.char.guid) end },
    { "sharePlaytime", L.SHARE_PLAYTIME },
    { "reloadReminder", L.RELOAD_REMINDER },
  } },
}

local settingChecks = {}

local function buildSettings(panel)
  panel.checks = {}
  local y = -44
  for _, group in ipairs(SETTINGS) do
    local header = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    header:SetPoint("TOPLEFT", 16, y)
    header:SetText(group[1])
    y = y - 22
    for _, item in ipairs(group[2]) do
      local key, label, set, get = item[1], item[2], item[3], item[4]
      local check = makeCheck(panel, label,
        get or function() return ns.db.settings[key] and true or false end,
        set or function(on) ns.db.settings[key] = on end)
      check:SetPoint("TOPLEFT", 20, y)
      panel.checks[key] = check
      settingChecks[#settingChecks + 1] = check
      y = y - 24
    end
    y = y - 14
  end
end

--- Les cases reprennent l'état des réglages à chaque ouverture (ils changent aussi ailleurs : /mf, dialogues).
local function showSettings()
  for _, check in ipairs(settingChecks) do check:SetChecked(check.get()) end
end

UI.AddTab({ key = "settings", order = 4, label = L.TAB_SETTINGS, name = "WoWForeverGuildeSettings", build = buildSettings, show = showSettings })

-- --- onglet Nouveautés : ce qui change, version par version -----------------------------------------------
--
-- Les notes sont dans ns.CHANGELOG (Locales/frFR.lua), la plus récente d'abord. On ne montre que celles des
-- versions qu'on a : une note écrite d'avance n'apparaît qu'une fois la version installée. La dernière version
-- dont on a lu les notes est retenue (`settings.changelogSeen`) : tant qu'il y en a une plus récente, l'onglet
-- est en vert et une ligne de chat le signale à la connexion.

local function knownNotes()
  local notes = {}
  for _, entry in ipairs(ns.CHANGELOG or {}) do
    if not ns.VersionNewer(entry.version, ns.VERSION) then notes[#notes + 1] = entry end
  end
  return notes
end

--- La version dont les notes n'ont pas encore été lues, s'il y en a une.
function UI.NewsUnseen()
  local newest = knownNotes()[1]
  if not newest or not ns.db then return nil end
  local seen = ns.db.settings.changelogSeen
  if seen and not ns.VersionNewer(newest.version, seen) then return nil end
  return newest.version
end

local function buildNews(panel)
  panel.scroll = CreateFrame("ScrollFrame", nil, panel, "UIPanelScrollFrameTemplate")
  panel.scroll:SetPoint("TOPLEFT", 16, -44)
  panel.scroll:SetPoint("BOTTOMRIGHT", -36, 16)
  panel.content = CreateFrame("Frame", nil, panel.scroll)
  panel.content:SetSize(WINDOW_WIDTH - 60, 100)
  panel.scroll:SetScrollChild(panel.content)
  panel.text = panel.content:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  panel.text:SetPoint("TOPLEFT", 0, 0)
  panel.text:SetWidth(WINDOW_WIDTH - 70)
  panel.text:SetJustifyH("LEFT")
end

local function showNews(panel)
  local notes = knownNotes()
  local seen = ns.db.settings.changelogSeen
  local out, count = {}, 0
  for i, entry in ipairs(notes) do
    -- Jamais rien lu : seule la dernière version est « nouvelle », pas tout l'historique.
    local fresh = (seen == nil and i == 1) or (seen ~= nil and ns.VersionNewer(entry.version, seen))
    out[#out + 1] = "|cffffd100" .. entry.version .. "|r" .. (fresh and ("  |cff5ad15a" .. L.NEWS_NEW .. "|r") or "")
    for _, note in ipairs(entry.notes or {}) do out[#out + 1] = "  – " .. note end
    out[#out + 1] = ""
    count = count + 2 + #(entry.notes or {})
  end
  panel.text:SetText(#notes > 0 and table.concat(out, "\n") or L.NEWS_EMPTY)
  local height = panel.text.GetStringHeight and panel.text:GetStringHeight() or 0
  panel.content:SetHeight(math.max(height or 0, count * 14, 100))
  if notes[1] then ns.db.settings.changelogSeen = notes[1].version end
  paintTabs()
end

UI.AddTab({
  key = "news", order = 5, label = L.TAB_NEWS, name = "WoWForeverGuildeNews", build = buildNews, show = showNews,
  badge = UI.NewsUnseen,
})

-- --- onglet Diagnostic : ce que /mf api et /mf erreurs disent, dans une zone à copier pour le GM ---------------

local function diagReport()
  local lines, client = ns.DiagnosticLines()
  local out = {
    string.format(L.DIAG_HEADER, tostring(ns.VERSION), tostring(ns.TOC_VERSION or "?"),
      client ~= "" and client or L.DIAG_NO_CLIENT, date("%d/%m/%Y %H:%M", ns.now())),
    "",
  }
  for _, line in ipairs(lines) do out[#out + 1] = line end
  out[#out + 1] = ""
  for _, line in ipairs(ns.ErrorLines(10)) do out[#out + 1] = line end
  return table.concat(out, "\n")
end

local function showDiag(panel)
  local ok, report = ns.Safe("diagnostic", diagReport)
  panel.report = ok and report or tostring(report)
  panel.box:SetText(panel.report)
end

local function buildDiag(panel)
  local refresh = makeButton(panel, L.DIAG_REFRESH, 100)
  refresh:SetPoint("TOPLEFT", 12, -42)
  refresh:SetScript("OnClick", function() showDiag(panel) end)
  local send = makeButton(panel, L.DIAG_SEND, 150)
  send:SetPoint("LEFT", refresh, "RIGHT", 8, 0)
  send:SetScript("OnClick", function() ns.Safe("diagnostic", ns.SaveDiagnostic) end)
  local trace = makeButton(panel, L.DIAG_TRACE, 120)
  trace:SetPoint("LEFT", send, "RIGHT", 8, 0)
  trace:SetScript("OnClick", function()
    ns.traceUntil = ns.now() + ns.Data.TRACE_SECONDS
    ns.Print(L.TRACE_ON, ns.Data.TRACE_SECONDS)
  end)
  panel.refresh, panel.send, panel.trace = refresh, send, trace

  local scroll = CreateFrame("ScrollFrame", nil, panel, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 16, -76)
  scroll:SetPoint("BOTTOMRIGHT", -36, 40)
  local box = CreateFrame("EditBox", nil, scroll)
  box:SetMultiLine(true)
  box:SetAutoFocus(false)
  box:SetFontObject(ChatFontSmall or GameFontHighlightSmall)
  box:SetWidth(WINDOW_WIDTH - 60)
  box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  -- Zone en lecture seule : une frappe remet le rapport, la sélection et la copie restent possibles.
  box:SetScript("OnTextChanged", function(self, user)
    if user and panel.report and self:GetText() ~= panel.report then self:SetText(panel.report) end
  end)
  scroll:SetScrollChild(box)
  panel.box = box
  panel.hint = panel:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  panel.hint:SetPoint("BOTTOMLEFT", 16, 18)
  panel.hint:SetText(L.DIAG_HINT)
end

UI.AddTab({ key = "diag", order = 6, label = L.TAB_DIAG, name = "WoWForeverGuildeDiag", build = buildDiag, show = showDiag })

-- --- bouton de la minimap : un clic ouvre la fenêtre -------------------------------------------------------
--
-- Fait à la main (pas de bibliothèque à embarquer) : un bouton rond accroché au bord de la minimap, qu'on fait
-- glisser autour ; son angle est retenu. Décochable dans les réglages. Sans minimap sur ce client, rien.

local minimapButton

local function placeMinimapButton()
  local angle = math.rad(ns.db.settings.minimapButtonAngle or 215)
  local radius = ((Minimap.GetWidth and Minimap:GetWidth()) or 140) / 2 + 6
  minimapButton:ClearAllPoints()
  minimapButton:SetPoint("CENTER", Minimap, "CENTER", math.cos(angle) * radius, math.sin(angle) * radius)
end

local function buildMinimapButton()
  local button = CreateFrame("Button", "WoWForeverGuildeMinimapButton", Minimap)
  minimapButton = button
  button:SetSize(31, 31)
  button:SetFrameStrata("MEDIUM")
  button:SetFrameLevel(8)
  button:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  button:RegisterForDrag("LeftButton")
  button:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
  button.icon = button:CreateTexture(nil, "BACKGROUND")
  button.icon:SetSize(19, 19)
  button.icon:SetPoint("TOPLEFT", 6, -6)
  button.icon:SetTexture(ns.Data.ICON)
  button.icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
  button.border = button:CreateTexture(nil, "OVERLAY")
  button.border:SetSize(53, 53)
  button.border:SetPoint("TOPLEFT", 0, 0)
  button.border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
  button:SetScript("OnClick", function(_, mouse)
    if mouse == "RightButton" then UI.Toggle("settings") else UI.Toggle() end
  end)
  -- Glissé : le bouton suit le curseur autour de la minimap, l'angle est retenu au fur et à mesure.
  button:SetScript("OnDragStart", function(self)
    self:SetScript("OnUpdate", function()
      local cx, cy = Minimap:GetCenter()
      local px, py = GetCursorPosition()
      local scale = Minimap:GetEffectiveScale()
      if not cx or not px or not scale or scale == 0 then return end
      ns.db.settings.minimapButtonAngle = math.deg(math.atan2(py / scale - cy, px / scale - cx)) % 360
      placeMinimapButton()
    end)
  end)
  button:SetScript("OnDragStop", function(self) self:SetScript("OnUpdate", nil) end)
  button:SetScript("OnEnter", function(self)
    if not GameTooltip then return end
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:ClearLines()
    GameTooltip:AddLine(L.TITLE .. " |cff9a9a9av" .. tostring(ns.VERSION) .. "|r", 1, 0.82, 0)
    GameTooltip:AddLine(L.MINIMAP_BUTTON_HINT, 0.9, 0.9, 0.9)
    local unseen = UI.NewsUnseen()
    if unseen then GameTooltip:AddLine(string.format(L.NEWS_CHAT, unseen), 0.35, 0.82, 0.35) end
    GameTooltip:Show()
  end)
  button:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
end

--- Montre ou cache le bouton de la minimap, et retient le choix.
function UI.SetMinimapButton(on)
  ns.db.settings.minimapButton = on and true or false
  if type(Minimap) ~= "table" then return end
  if on then
    if not minimapButton then buildMinimapButton() end
    placeMinimapButton()
    minimapButton:Show()
  elseif minimapButton then
    minimapButton:Hide()
  end
end

-- --- dialogues ---------------------------------------------------------------------------------------

-- Fenêtre de dialogue propre à l'addon : une seule, réutilisée, une question à la fois (les suivantes attendent).
-- On ne passe pas par les dialogues du jeu (StaticPopup) : un addon qui les affiche ou y écrit (`dialog.data`) les
-- contamine, et le jeu refuse ensuite ses propres actions protégées depuis ces mêmes fenêtres (vu en jeu :
-- ADDON_ACTION_BLOCKED sur CancelLogout(), la déconnexion ne s'annulait plus). Pas de fermeture par Échap : chaque
-- dialogue a son bouton « plus tard ».
-- Une définition : { button1, button2, button3, OnAccept = fn(dialog, data), OnAlt = fn(dialog, data) } ;
-- bouton 1 = OnAccept, bouton 2 = fermer, bouton 3 = OnAlt.
UI.Dialogs = {}
local dialogFrame = nil
local dialogQueue = {}

local function showNextDialog()
  local f = dialogFrame
  if not f or f:IsShown() then return end
  local request = table.remove(dialogQueue, 1)
  if not request then return end
  local def = UI.Dialogs[request.which]
  f.which, f.data, f.message = request.which, request.data, request.text
  f.text:SetText(request.text)
  local labels, shown = { def.button1, def.button2, def.button3 }, {}
  for i, button in ipairs(f.buttons) do
    if labels[i] then
      button:SetText(labels[i])
      button:Show()
      shown[#shown + 1] = button
    else
      button:Hide()
    end
  end
  local width, gap = 120, 8
  local total = #shown * width + (#shown - 1) * gap
  for i, button in ipairs(shown) do
    button:ClearAllPoints()
    button:SetPoint("BOTTOMLEFT", f, "BOTTOM", -total / 2 + (i - 1) * (width + gap), 16)
  end
  f:Show()
end

local function buildDialog()
  local f = CreateFrame("Frame", "WoWForeverGuildeDialog", UIParent, "BackdropTemplate")
  f:SetSize(420, 150)
  f:SetPoint("TOP", UIParent, "TOP", 0, -140)
  f:SetFrameStrata("DIALOG")
  f:EnableMouse(true)
  if f.SetBackdrop then
    f:SetBackdrop({
      bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark",
      edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border", edgeSize = 24,
      insets = { left = 6, right = 6, top = 6, bottom = 6 },
    })
  end
  f.text = f:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  f.text:SetPoint("TOP", 0, -20)
  f.text:SetWidth(380)
  f.text:SetJustifyH("CENTER")
  f.buttons = {}
  for i = 1, 3 do
    local button = makeButton(f, "", 120)
    button:SetScript("OnClick", function()
      local def, data = UI.Dialogs[f.which], f.data
      f:Hide()
      local handler = def and ((i == 1 and def.OnAccept) or (i == 3 and def.OnAlt)) or nil
      if handler then ns.Safe("ui.dialog", handler, f, data) end
      showNextDialog()
    end)
    f.buttons[i] = button
  end
  f:Hide()
  return f
end

--- Pose la question `which` (une clé de UI.Dialogs) avec ce texte ; `data` revient aux fonctions des boutons.
function UI.ShowDialog(which, text, data)
  if not UI.Dialogs[which] then return end
  dialogFrame = dialogFrame or buildDialog()
  -- La même question déjà posée (affichée ou en attente) n'est pas empilée une seconde fois.
  if dialogFrame:IsShown() and dialogFrame.which == which then return end
  for _, request in ipairs(dialogQueue) do
    if request.which == which then return end
  end
  dialogQueue[#dialogQueue + 1] = { which = which, text = text, data = data }
  showNextDialog()
end

UI.Dialogs.WFG_TRANSFER = {
  button1 = L.TRANSFER_YES,
  button2 = L.TRANSFER_NO,
  OnAccept = function(self, data)
    ns.Store.Merge(data.entry, data.candidate)
    ns.Print(L.TRANSFER_DONE)
  end,
}

function UI.AskTransfer(entry, candidate)
  local class = ns.ClassLabel(candidate.class) -- le nom de la classe (« Chaman »), pas son jeton (« SHAMAN »)
  local text = string.format(L.TRANSFER_TEXT, UnitName("player") or "?", candidate.name or "?", class ~= "" and class or "?", candidate.level or 0)
  UI.ShowDialog("WFG_TRANSFER", text, { entry = entry, candidate = candidate })
end

UI.Dialogs.WFG_RELOAD = {
  button1 = L.RELOAD_YES,
  button2 = L.RELOAD_LATER,
  button3 = L.RELOAD_NEVER,
  OnAccept = function() ReloadUI() end,
  OnAlt = function() ns.db.settings.reloadReminder = false end,
}

function UI.SuggestReload(unsaved)
  UI.ShowDialog("WFG_RELOAD", string.format(L.RELOAD_TEXT, duration(unsaved)))
end

UI.Dialogs.WFG_UPGRADE = {
  button1 = L.UPGRADE_YES,
  button2 = L.UPGRADE_LATER,
  OnAccept = function(self, version) ns.UpgradeAccepted(version) end,
}

--- Un guildien a une version plus récente de l'addon : proposer le /reload (le compagnon a déjà copié les fichiers).
function UI.SuggestUpgrade(version)
  UI.ShowDialog("WFG_UPGRADE", string.format(L.UPGRADE_TEXT, version, tostring(ns.VERSION)), version)
end

function UI.OnLogin(entry)
  ns.Print(L.WELCOME, entry.name or UnitName("player") or "", dateText(entry.counting_since))
  local recent = 0
  for _, e in ipairs((ns.db and ns.db.errors) or {}) do
    if (e.t or 0) >= ns.now() - 86400 then recent = recent + 1 end
  end
  if recent > 0 then ns.Print(L.ERRORS_RECENT, recent) end
  local unseen = UI.NewsUnseen()
  if unseen then ns.Print(L.NEWS_CHAT, unseen) end
  ns.Safe("ui.minimap", UI.SetMinimapButton, ns.db.settings.minimapButton)
end

-- --- voix : séries de kills et primes encaissées ------------------------------------------------------------
--
-- Fichiers du dossier Sounds de l'addon (ns.Data.VOICES). Une voix coupe la précédente encore en cours : deux
-- kills coup sur coup ne se superposent pas.

local lastVoice = nil -- /mf api : dernier fichier demandé au jeu et sa réponse
local lastVoiceAt, lastVoiceHandle = nil, nil

--- Joue une voix (clé de ns.Data.VOICES) ; vrai si le jeu l'a lue (faux : fichier absent, client sans lecteur).
function UI.PlayVoice(key)
  local file = ns.Data.VOICES[key]
  if not file then return false end
  if type(PlaySoundFile) ~= "function" then
    lastVoice = file .. " : ce client ne lit pas de fichier son"
    return false
  end
  if lastVoiceHandle and type(StopSound) == "function" then pcall(StopSound, lastVoiceHandle) end
  local ok, played, handle = pcall(PlaySoundFile, ns.Data.SOUNDS_DIR .. file, "Master")
  played = ok and played and true or false
  lastVoiceHandle = played and handle or nil
  if played then lastVoiceAt = ns.now() end
  lastVoice = file .. (played and " : joué" or " : pas joué (fichier absent de Sounds\\, ou jeu pas relancé depuis son ajout)")
  return played
end

--- Une voix vient-elle de partir (moins de VOICE_OVERLAP s) ?
function UI.VoiceJustPlayed()
  return lastVoiceAt ~= nil and ns.now() - lastVoiceAt < ns.Data.VOICE_OVERLAP
end

function UI.VoiceSource()
  return lastVoice or "aucune voix demandée cette session"
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
  toastLog[#toastLog + 1] = { t = ns.now(), what = what, label = ns.Cut(label, 60) }
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
--- `quiet` : noté dans l'historique sans popup (« Afficher les morts des autres » décoché).
function UI.ShowDeath(info, phrase, wanted, quiet)
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
  local label = string.format(L.DEATH_LOG, ns.DeathName(info), info.killer or "")
  local footer, key = table.concat(parts, " · "), "mort:" .. tostring(info.name)
  UI.Remember("death", key, phrase, footer)
  if quiet then return end
  UI.ShowToast(header, phrase, footer, { 1, 0.35, 0.24 }, ns.db.settings.soundDeaths, key, label)
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
--- `quiet` : noté dans l'historique sans popup (« Afficher les morts des autres » décoché).
function UI.ShowKill(victim, hunters, phrase, place, id, updateOnly, quiet)
  place = place ~= "" and place or L.WHERE_UNKNOWN
  local key = "kill:" .. tostring(id or victim)
  UI.Remember("kill", key, phrase, place)
  if quiet or (updateOnly and not UI.ToastPending(key)) then return end
  local label = string.format(#hunters > 1 and L.KILL_LOG_PLURAL or L.KILL_LOG, ns.Wanted.HunterNames(hunters), victim, place)
  UI.ShowToast(L.KILL_HEADER, phrase, place, { 0.45, 0.9, 0.45 }, false, key, label)
end

--- Prime encaissée : un recherché abattu par un membre (moi ou un autre). Or, son si les morts en ont un. La
--- phrase (Wanted.BountyPhrase) arrive prête ; le pied donne la prime et le lieu.
function UI.ShowBounty(entry, phrase, by, prime, place)
  place = place ~= "" and place or L.WHERE_UNKNOWN
  local label = string.format(L.BOUNTY_LOG, by, entry.name, ns.Points(prime), place)
  local footer = string.format(L.BOUNTY_FOOTER, ns.Points(prime), place)
  UI.Remember("bounty", nil, phrase, footer)
  -- La voix d'une prime (0.7.2), celle des grosses primes à partir de BOUNTY_BIG points ; sans elle (case décochée,
  -- fichier absent), le bip habituel. La série du même kill vient de parler : la prime reste muette.
  local s, beep = ns.db.settings, ns.db.settings.soundDeaths
  if s.soundStreaks then
    if UI.VoiceJustPlayed() or UI.PlayVoice((prime or 0) >= ns.Data.BOUNTY_BIG and "bountyBig" or "bounty") then
      beep = false
    end
  end
  UI.ShowToast(L.BOUNTY_HEADER, phrase, footer, { 1, 0.82, 0 }, beep, nil, label)
end

-- --- séries de kills : de « double kill » à « monster kill » --------------------------------------------------
--
-- Un texte à part, au-dessus des popups, hors de leur file d'attente : la voix part à l'instant du kill. Sans
-- fichier dans Sounds\, le texte s'affiche seul.

local streakFrame

local function buildStreak()
  streakFrame = CreateFrame("Frame", "WoWForeverGuildeStreak", UIParent)
  streakFrame:SetSize(900, 80)
  streakFrame:SetPoint("TOP", 0, -24)
  streakFrame:SetFrameStrata("HIGH")
  streakFrame:EnableMouse(false)
  streakFrame.title = streakFrame:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge")
  streakFrame.title:SetPoint("TOP", 0, 0)
  streakFrame.title:SetTextColor(1, 0.25, 0.15)
  streakFrame.title:SetShadowOffset(2, -2)
  streakFrame.names = streakFrame:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  streakFrame.names:SetPoint("TOP", streakFrame.title, "BOTTOM", 0, -6)
  streakFrame:Hide()
end

function UI.StreakSource()
  return UI.VoiceSource()
end

--- Série de kills d'un ou de plusieurs chasseurs. `level` : le palier ; `fresh` : une nouvelle série (texte et
--- voix), sinon un chasseur de plus sur le texte encore affiché ; `force` : même réglages décochés (/mf serie).
function UI.ShowStreak(level, hunters, fresh, force)
  local s = ns.db.settings
  if not level then return end
  if fresh and (s.soundStreaks or force) then UI.PlayVoice(level) end
  if not (s.showStreaks or force) then return end
  if not streakFrame then buildStreak() end
  if not fresh and not streakFrame:IsShown() then return end
  streakFrame.title:SetText(L["STREAK_" .. level])
  streakFrame.names:SetText(ns.Wanted.HunterNames(hunters, true))
  if not fresh then return end
  if streakFrame.timer then streakFrame.timer:Cancel() end
  streakFrame:SetAlpha(0)
  streakFrame:Show()
  UIFrameFadeIn(streakFrame, 0.2, 0, 1)
  streakFrame.timer = C_Timer.NewTimer(ns.Data.STREAK_SECONDS, function() streakFrame:Hide() end)
end
