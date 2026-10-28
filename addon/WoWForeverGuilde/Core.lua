-- Démarrage, bus d'événements, cycle de vie, protection des collecteurs. Rien n'est écrit sur le disque par
-- l'addon : le client écrit WoWForeverGuildeDB à la déconnexion et au /reload.
local ADDON, ns = ...

ns.ADDON = ADDON
do
  local meta = (C_AddOns and C_AddOns.GetAddOnMetadata) or GetAddOnMetadata
  ns.VERSION = (meta and meta(ADDON, "Version")) or "dev"
end

ns.collectors = {}
ns.sessionStart = nil
ns.lastWrite = nil

--- Valeur « secrète » (Forever) → nil, pour ne jamais provoquer d'erreur en la lisant.
function ns.plain(value)
  if issecretvalue and issecretvalue(value) then return nil end
  return value
end

function ns.Print(fmt, ...)
  local text = select("#", ...) > 0 and string.format(fmt, ...) or fmt
  DEFAULT_CHAT_FRAME:AddMessage(ns.L.CHAT_PREFIX .. text)
end

--- Exécute protégé : une erreur est journalisée dans la base (et jointe au prochain export), jamais affichée.
function ns.Safe(where, fn, ...)
  local ok, err = pcall(fn, ...)
  if not ok then ns.Store.LogError(where, err) end
  return ok, err
end

function ns.InCombat()
  return (InCombatLockdown and InCombatLockdown()) or (UnitAffectingCombat and UnitAffectingCombat("player")) or false
end

-- File d'attente hors combat.
local deferred = {}
function ns.Defer(fn)
  if ns.InCombat() then
    deferred[#deferred + 1] = fn
  else
    fn()
  end
end

local function flushDeferred()
  local queue = deferred
  deferred = {}
  for _, fn in ipairs(queue) do fn() end
end

-- Regroupement : plusieurs événements rapprochés → une seule lecture.
local pending = {}
function ns.Debounce(key, delay, fn)
  if pending[key] then return end
  pending[key] = true
  C_Timer.After(delay, function()
    pending[key] = nil
    ns.Defer(fn)
  end)
end

--- Déclare un collecteur : { name, events = {...}, scan = fn(char), onEvent = fn(char, event, ...),
--- onLogout = fn(char), status = fn(char) -> texte }.
function ns.RegisterCollector(def)
  ns.collectors[#ns.collectors + 1] = def
end

function ns.Char()
  return ns.char
end

local frame = CreateFrame("Frame")
ns.frame = frame
local registered = {}

local function registerEvent(event)
  if not registered[event] then
    registered[event] = true
    pcall(frame.RegisterEvent, frame, event)
  end
end

local function runScan(def)
  if def.scan and ns.char then
    ns.Debounce("scan:" .. def.name, 1, function()
      ns.Safe(def.name .. ".scan", def.scan, ns.char)
      ns.char.updated_at = ns.now()
    end)
  end
end

local function dispatch(event, ...)
  for _, def in ipairs(ns.collectors) do
    if def.events and def.events[event] then
      if def.onEvent then ns.Safe(def.name .. ".onEvent", def.onEvent, ns.char, event, ...) end
      if def.scanOn and def.scanOn[event] then runScan(def) end
    end
  end
end

function ns.FullScan()
  for _, def in ipairs(ns.collectors) do runScan(def) end
end

local function onLogin()
  ns.sessionStart = ns.now()
  local guid = UnitGUID("player")
  if not guid then return end
  local entry = ns.Store.Character(guid)
  ns.char = entry
  -- Identité minimale tout de suite (sert à la détection de transfert).
  local _, classToken = UnitClass("player")
  local _, raceToken = UnitRace("player")
  local level = UnitLevel("player")
  if entry.created_at == entry.updated_at and entry.class == nil then
    local candidate = ns.Store.FindTransferCandidate(guid, classToken, raceToken, level)
    if candidate and ns.UI and ns.UI.AskTransfer then ns.UI.AskTransfer(entry, candidate) end
  end
  entry.class, entry.race, entry.level = classToken, raceToken, level
  entry.faction = UnitFactionGroup and UnitFactionGroup("player") or nil

  for _, def in ipairs(ns.collectors) do
    for event in pairs(def.events or {}) do registerEvent(event) end
    if def.onLogin then ns.Safe(def.name .. ".onLogin", def.onLogin, entry) end
  end
  ns.Journal.Rollover(entry, ns.now())
  C_Timer.After(3, ns.FullScan)
  C_Timer.NewTicker(60, function() ns.Safe("tick", ns.Tick) end)
  if ns.UI and ns.UI.OnLogin then ns.Safe("UI.OnLogin", ns.UI.OnLogin, entry) end
end

function ns.Tick()
  local entry = ns.char
  if not entry then return end
  local t = ns.now()
  ns.Journal.Rollover(entry, t)
  if ns.db.settings.reloadReminder and not ns.reloadAsked and ns.UI and ns.UI.SuggestReload then
    local unsaved = t - (ns.lastWrite or ns.sessionStart or t)
    local calm = not ns.InCombat() and not (IsInInstance and IsInInstance()) and not (IsInGroup and IsInGroup())
    if unsaved >= ns.Data.RELOAD_REMINDER_SECONDS and calm then
      ns.reloadAsked = true
      ns.UI.SuggestReload(unsaved)
    end
  end
end

local function onLogout()
  local entry = ns.char
  if not entry then return end
  local t = ns.now()
  for _, def in ipairs(ns.collectors) do
    if def.onLogout then ns.Safe(def.name .. ".onLogout", def.onLogout, entry) end
    if def.scan then ns.Safe(def.name .. ".scan", def.scan, entry) end
  end
  entry.updated_at = t
  ns.Journal.Snapshot(entry, t)
  ns.Safe("Export.Build", ns.Export.Build, t)
  ns.db.last_write = t
end

frame:SetScript("OnEvent", function(_, event, ...)
  if event == "ADDON_LOADED" then
    if ... == ADDON then
      ns.Store.Init()
      frame:UnregisterEvent("ADDON_LOADED")
    end
  elseif event == "PLAYER_LOGIN" then
    ns.Safe("login", onLogin)
  elseif event == "PLAYER_LOGOUT" then
    ns.Safe("logout", onLogout)
  elseif event == "PLAYER_REGEN_ENABLED" then
    flushDeferred()
  else
    dispatch(event, ...)
  end
end)
frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("PLAYER_LOGOUT")
frame:RegisterEvent("PLAYER_REGEN_ENABLED")

SLASH_WOWFOREVERGUILDE1 = "/wfg" -- provisoire : acronyme du nom de la guilde à venir (cahier des charges)
SlashCmdList.WOWFOREVERGUILDE = function(msg)
  msg = (msg or ""):lower()
  if msg == "export" and ns.UI then ns.UI.ShowExport()
  elseif msg == "save" or msg == "reload" then ReloadUI()
  elseif ns.UI then ns.UI.Toggle() end
end
