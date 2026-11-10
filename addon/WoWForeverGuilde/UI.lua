-- Interface : fenêtre /mf (personnages, état de la collecte, export, sauvegarde), fenêtre d'export,
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
UI.MakeFrame = makeFrame

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

-- --- fenêtre principale ---------------------------------------------------------------------------

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

local function buildMain()
  main = makeFrame("WoWForeverGuildeFrame", 700, 482, L.TITLE)
  main.version = main:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  main.version:SetPoint("LEFT", main.title, "RIGHT", 10, 0)
  main.version:SetText("v" .. tostring(ns.VERSION))

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
  -- Une seule rangée de boutons, alignés en bas de la fenêtre.
  main.rosterButton = makeButton(main, L.ROSTER_BUTTON, 118)
  main.rosterButton:SetPoint("BOTTOMLEFT", 12, 12)
  main.rosterButton:SetScript("OnClick", function() ns.RosterUI.Toggle() end)
  main.wantedButton = makeButton(main, L.WANTED_BUTTON, 90)
  main.wantedButton:SetPoint("LEFT", main.rosterButton, "RIGHT", 8, 0)
  main.wantedButton:SetScript("OnClick", function() ns.WantedUI.Toggle() end)
  main.sosButton = makeButton(main, L.SOS_BUTTON, 118)
  main.sosButton:SetPoint("LEFT", main.wantedButton, "RIGHT", 8, 0)
  main.sosButton:SetScript("OnClick", function() ns.Positions.SOS() end)
  main.exportButton = makeButton(main, L.EXPORT, 130)
  main.exportButton:SetPoint("LEFT", main.sosButton, "RIGHT", 8, 0)
  main.exportButton:SetScript("OnClick", function() UI.ShowExport() end)
  main.saveButton = makeButton(main, L.SAVE_NOW, 170)
  main.saveButton:SetPoint("LEFT", main.exportButton, "RIGHT", 8, 0)
  main.saveButton:SetScript("OnClick", function() ReloadUI() end)
  main.hint = main:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  main.hint:SetPoint("BOTTOMRIGHT", -16, 44)
  main.hint:SetText(L.REOPEN)
  main:SetScript("OnShow", UI.Refresh)
end

function UI.Refresh()
  if not main or not main:IsShown() then return end
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

function UI.Toggle()
  if not main then buildMain() end
  if main:IsShown() then main:Hide() else main:Show() end
end

-- --- fenêtre d'export -----------------------------------------------------------------------------

local exportFrame

local function buildExport()
  exportFrame = makeFrame("WoWForeverGuildeExport", 560, 420, L.EXPORT_TITLE)
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
  box:SetWidth(500)
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
  regen:SetScript("OnClick", function() UI.ShowExport() end)
  local warn = exportFrame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  warn:SetPoint("BOTTOMRIGHT", -16, 26)
  warn:SetText(L.TRUNCATED_WARNING)
end

function UI.ShowExport()
  if not exportFrame then buildExport() end
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
  exportFrame:Show()
  exportFrame.box:SetFocus()
  exportFrame.box:HighlightText()
end

-- --- dialogues ---------------------------------------------------------------------------------------

StaticPopupDialogs["WFG_TRANSFER"] = {
  text = "%s",
  button1 = L.TRANSFER_YES,
  button2 = L.TRANSFER_NO,
  OnAccept = function(self, data)
    ns.Store.Merge(data.entry, data.candidate)
    ns.Print("Compteurs conservés.")
  end,
  timeout = 0, whileDead = true, hideOnEscape = false, preferredIndex = 3,
}

function UI.AskTransfer(entry, candidate)
  local text = string.format(L.TRANSFER_TEXT, UnitName("player") or "?", candidate.name or "?", candidate.class or "?", candidate.level or 0)
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
local waiting, shownAt, shownKey, nextTimer = {}, nil, nil, nil

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
  toast.timer = C_Timer.NewTimer(ns.Data.TOAST_SECONDS, function()
    UIFrameFadeOut(toast, 1, 1, 0)
    C_Timer.After(1, function() toast:Hide() end)
  end)
end

local function showNext()
  nextTimer = nil
  local item = table.remove(waiting, 1)
  if not item then return end
  display(item[1], item[2], item[3], item[4], item[5], item[6])
  if #waiting > 0 then nextTimer = C_Timer.NewTimer(ns.Data.TOAST_MIN_SECONDS, showNext) end
end

function UI.ShowToast(headerText, text, footer, color, sound, key)
  if not toast then buildToast() end
  local busy = toast:IsShown() and shownAt and ns.now() - shownAt < ns.Data.TOAST_MIN_SECONDS
  if (not busy and #waiting == 0) or (key and toast:IsShown() and key == shownKey) then
    display(headerText, text, footer, color, sound, key)
    return
  end
  for i, item in ipairs(waiting) do
    if key and item[6] == key then -- encore en attente : corrigé à sa place dans la file
      waiting[i] = { headerText, text, footer, color, sound, key }
      return
    end
  end
  waiting[#waiting + 1] = { headerText, text, footer, color, sound, key }
  while #waiting > ns.Data.TOAST_QUEUE do table.remove(waiting, 1) end
  if not nextTimer then
    nextTimer = C_Timer.NewTimer(math.max(0.1, ns.Data.TOAST_MIN_SECONDS - (ns.now() - (shownAt or 0))), showNext)
  end
end

--- Avis de décès ; `wanted` : l'entrée du tueur dans le tableau Wanted, quand c'est un joueur recherché, et que
--- les alertes Wanted sont cochées : l'en-tête et le pied portent alors la prime (un seul cadre flottant, pas deux).
function UI.ShowDeath(info, phrase, wanted)
  local color = RAID_CLASS_COLORS and RAID_CLASS_COLORS[(info.class or ""):upper()]
  local coloredName = color and ("|c" .. (color.colorStr or "ffffffff") .. info.name .. "|r") or info.name
  -- Remplacement littéral : un nom n'est pas un motif Lua.
  local at = phrase:find(info.name, 1, true)
  if at then phrase = phrase:sub(1, at - 1) .. coloredName .. phrase:sub(at + #info.name) end
  local header, footer = L.DEATH_HEADER, string.format(L.DEATH_FOOTER, info.level or 0, ns.ClassLabel(info.class))
  if info.player then
    -- Mort PvP : toujours dite « WANTED », même sans les alertes Wanted (alors sans la prime), et le tueur à la
    -- couleur de sa classe (seuls les joueurs en ont une). La phrase, elle, reste tirée du même lot.
    header, footer = L.DEATH_WANTED_HEADER, string.format(L.DEATH_PVP_FOOTER, info.level or 0, ns.ClassLabel(info.class))
    local killer = info.killer or ""
    if killer ~= "" and info.kclass and info.kclass ~= "" then
      local from = phrase:find(killer, 1, true)
      if from then phrase = phrase:sub(1, from - 1) .. ns.ClassColored(killer, info.kclass) .. phrase:sub(from + #killer) end
    end
  end
  if wanted and ns.db.settings.wantedAlerts then
    header = L.DEATH_WANTED_HEADER
    footer = string.format(L.DEATH_WANTED_FOOTER, info.level or 0, ns.ClassLabel(info.class), wanted.points or 0)
  end
  UI.ShowToast(header, phrase, footer, { 1, 0.35, 0.24 }, ns.db.settings.soundDeaths, "mort:" .. tostring(info.name))
end

--- Appel à l'aide d'un membre dans ma zone.
function UI.ShowAlert(peer, text)
  UI.ShowToast(L.ALERT_HEADER, text, ns.Positions.Where(peer), { 1, 0.62, 0.2 }, true)
end

--- Victoire honorable : un joueur adverse abattu par un membre (moi ou un autre), hors champ de bataille. Vert,
--- sans son (il y en a bien plus que de morts) ; chasseur et victime à la couleur de leur classe.
--- `hunters` : { { name, class }, … }, tous ceux du kill ; un chasseur de plus complète le popup sur place (même clé).
function UI.ShowKill(victim, victimClass, hunters, phrase, place)
  local who = { { victim, victimClass } }
  for _, h in ipairs(hunters) do who[#who + 1] = { h.name, h.class } end
  for _, w in ipairs(who) do
    local at = phrase:find(w[1], 1, true) -- remplacement littéral : un nom n'est pas un motif Lua
    if at and w[2] and w[2] ~= "" then
      phrase = phrase:sub(1, at - 1) .. ns.ClassColored(w[1], w[2]) .. phrase:sub(at + #w[1])
    end
  end
  local footer = string.format(#hunters > 1 and L.KILL_FOOTER_PLURAL or L.KILL_FOOTER, ns.Wanted.HunterNames(hunters, true),
    ns.ClassColored(victim, victimClass), place ~= "" and place or L.WHERE_UNKNOWN)
  UI.ShowToast(L.KILL_HEADER, phrase, footer, { 0.45, 0.9, 0.45 }, false, "kill:" .. tostring(victim))
end

--- Prime encaissée : un recherché abattu par un membre (moi ou un autre). Or, son si les morts en ont un.
function UI.ShowBounty(entry, phrase, by, byClass, prime, place)
  local footer = string.format(L.BOUNTY_FOOTER, ns.ClassColored(by, byClass), ns.ClassColored(entry.name, entry.class),
    string.format(prime > 1 and L.POINTS_PLURAL or L.POINTS_SINGULAR, prime), place ~= "" and place or L.WHERE_UNKNOWN)
  UI.ShowToast(L.BOUNTY_HEADER, phrase, footer, { 1, 0.82, 0 }, ns.db.settings.soundDeaths)
end
