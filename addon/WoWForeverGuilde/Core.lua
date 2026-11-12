-- Démarrage, bus d'événements, cycle de vie, protection des collecteurs. Rien n'est écrit sur le disque par
-- l'addon : le client écrit WoWForeverGuildeDB à la déconnexion et au /reload.
local ADDON, ns = ...

ns.ADDON = ADDON
-- La version du code, à monter avec `## Version` du .toc (un test garde les deux égales). C'est elle qui fait foi :
-- le client ne lit le .toc qu'à son lancement, alors qu'un /reload relit ce fichier. Après une mise à jour copiée
-- pendant que le jeu tourne, le .toc en mémoire donne encore l'ancien numéro (ns.TOC_VERSION) : l'addon se
-- croirait en retard et redemanderait sans fin de recharger.
local CODE_VERSION = "0.7.1"
do
  local meta = (C_AddOns and C_AddOns.GetAddOnMetadata) or GetAddOnMetadata
  ns.TOC_VERSION = meta and meta(ADDON, "Version") or nil
  ns.VERSION = CODE_VERSION
end

ns.collectors = {}
ns.sessionStart = nil
ns.lastWrite = nil

--- Valeur « secrète » (Forever) → nil, pour ne jamais provoquer d'erreur en la lisant.
function ns.plain(value)
  if issecretvalue and issecretvalue(value) then return nil end
  return value
end

--- Les `bytes` premiers octets d'un texte, sans couper une lettre accentuée en deux : un texte tronqué au milieu
--- d'un caractère n'est plus de l'UTF-8 valide, et part ainsi dans le chat, le diagnostic et vers le site.
function ns.Cut(text, bytes)
  if #text <= bytes then return text end
  -- Tant que l'octet suivant la coupe est un octet de suite (10xxxxxx), la coupe tombe dans un caractère.
  while bytes > 0 do
    local following = text:byte(bytes + 1)
    if not following or following < 128 or following >= 192 then break end
    bytes = bytes - 1
  end
  return text:sub(1, bytes)
end

local function unitNames(read, unit, realm, squashed)
  if not read then return nil end
  local first, second = read(unit)
  first, second = ns.plain(first), ns.plain(second)
  if type(first) ~= "string" or first == "" then return nil end
  local head, rest = first:match("^(%S+)%s+(.+)$")
  if head then return head, rest end
  if type(second) ~= "string" or second == "" or second == realm or second == squashed then second = nil end
  return first, second
end

--- Prénom et nom de famille d'une unité. Sur Forever, UnitFullName et UnitName rendent « prénom, nom de
--- famille » en deux valeurs (parfois « Prénom Nom » d'un seul tenant) ; ailleurs la seconde est le royaume.
function ns.UnitNames(unit)
  local realm = GetRealmName and GetRealmName()
  local squashed = type(realm) == "string" and realm:gsub("%s", "") or nil
  local first, surname = unitNames(UnitFullName, unit, realm, squashed)
  if not surname then
    local name, second = unitNames(UnitName, unit, realm, squashed)
    first, surname = first or name, second
  end
  return first, surname
end

--- « Prénom Nom » d'une unité (le prénom seul si le jeu ne donne rien d'autre) ; nil si le nom est illisible
--- (secret en combat, unité absente).
function ns.UnitDisplayName(unit)
  local ok, first, surname = pcall(ns.UnitNames, unit)
  if not ok or not first then return nil end
  return surname and (first .. " " .. surname) or first
end

--- En champ de bataille ou en arène : le Wanted est hors jeu (ni annonce de mort, ni point, ni prime).
function ns.InBattleground()
  local ok, inside, kind = pcall(IsInInstance or function() end)
  if not ok then return false end
  kind = ns.plain(kind)
  return ns.plain(inside) == true and (kind == "pvp" or kind == "arena") or false
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

--- Dernier appel « sensible » (API que le jeu pourrait réserver à son interface) : quand le jeu refuse un appel
--- sans en donner le nom, on sait au moins ce qu'on venait de faire. Pose le marqueur puis appelle.
ns.lastRisky = nil
function ns.Risky(name, fn, ...)
  ns.lastRisky = { name = name, t = ns.now() }
  return fn(...)
end

--- Les dernières erreurs des collecteurs (gardées dans le fichier, envoyées au site), une ligne chacune.
function ns.ErrorLines(limit)
  local errors = (ns.db and ns.db.errors) or {}
  if #errors == 0 then return { ns.L.ERRORS_NONE } end
  limit = limit or 10
  local first = math.max(1, #errors - limit + 1)
  local lines = { string.format(ns.L.ERRORS_HEADER, #errors, #errors - first + 1) }
  for i = first, #errors do
    local e = errors[i]
    lines[#lines + 1] = string.format("%s · %s · %s", date("%d/%m %H:%M", e.t or 0), tostring(e.where or "?"), tostring(e.error or "?"))
  end
  return lines
end

--- /mf erreurs : les mêmes, dans le chat.
function ns.PrintErrors(limit)
  for _, line in ipairs(ns.ErrorLines(limit)) do ns.Print("%s", line) end
end

function ns.Char()
  return ns.char
end

-- /mf trace : pendant TRACE_SECONDS, chaque message addon envoyé ou reçu est affiché (type, expéditeur, réponse du
-- jeu, raison d'un rejet), pour comprendre pourquoi un appel ou une mort n'arrive pas chez quelqu'un.
ns.traceUntil = 0
function ns.Trace(fmt, ...)
  if ns.now() > (ns.traceUntil or 0) then return end
  ns.Print("|cff9a9a9atrace ·|r " .. fmt, ...)
end

-- /mf api : ce que ce client offre pour les talents, les métiers, la carte et les messages addon, et ce que les
-- collecteurs en ont tiré. Affiché dans le chat et noté (où = « diagnostic ») pour partir au site avec les erreurs :
-- le GM le lit dans « Tests en jeu » sans copier-coller depuis l'autre PC.
local PROBES = {
  { "talents", {
    "GetNumTalentTabs", "GetNumTalents", "GetTalentInfo", "GetTalentTabInfo",
    "C_SpecializationInfo.GetTalentInfo", "C_SpecializationInfo.GetNumTalentTabs",
    "C_ClassTalents.GetActiveConfigID", "C_Traits.GetConfigInfo",
  } },
  { "métiers", {
    "GetProfessions", "GetProfessionInfo", "GetNumSkillLines", "GetSkillLineInfo",
    "C_TradeSkillUI.GetBaseProfessionInfo", "C_TradeSkillUI.GetChildProfessionInfo",
    "C_TradeSkillUI.GetProfessionInfoBySkillLineID", "C_TradeSkillUI.GetTradeSkillLine",
    "C_TradeSkillUI.GetAllRecipeIDs", "C_TradeSkillUI.GetRecipeInfo",
    "GetNumTradeSkills", "GetTradeSkillInfo", "GetTradeSkillRecipeLink", "GetTradeSkillLine",
    "GetNumCrafts", "GetCraftInfo", "GetCraftRecipeLink",
  } },
  { "carte", {
    "C_Map.GetBestMapForUnit", "C_Map.GetPlayerMapPosition", "C_ChatInfo.RegisterAddonMessagePrefix",
    "C_ChatInfo.SendAddonMessage", "IsInGuild", "GetNumGuildMembers", "GetGuildRosterInfo",
  } },
  { "mort", { "C_DeathInfo.GetDeathRecapEvents", "GetDeathRecapEvents", "GetDeathRecapLink" } },
  { "wanted", {
    "UnitIsPlayer", "UnitIsDeadOrGhost", "GetPVPLifetimeStats", "GetPVPSessionStats", "COMBATLOG_HONORGAIN",
    "COMBATLOG_HONORGAIN_NO_RANK", "COMBATLOG_XPGAIN_FIRSTPERSON",
  } },
  { "récolte", { "C_Spell.GetSpellName", "GetSpellInfo", "UnitChannelInfo" } },
}

local function resolve(path)
  local value = _G
  for part in path:gmatch("[^.]+") do
    if type(value) ~= "table" then return nil end
    value = value[part]
  end
  return value
end

--- Les lignes du diagnostic, et le client du jeu (« client 1.16.0 (12345, 16001) », ou vide).
function ns.DiagnosticLines()
  local lines = {}
  for _, group in ipairs(PROBES) do
    local have, miss = {}, {}
    for _, name in ipairs(group[2]) do
      if resolve(name) ~= nil then have[#have + 1] = name else miss[#miss + 1] = name end
    end
    lines[#lines + 1] = string.format("%s · présent : %s · absent : %s", group[1],
      #have > 0 and table.concat(have, ", ") or "rien", #miss > 0 and table.concat(miss, ", ") or "rien")
  end
  local char = ns.char or {}
  local professions = {}
  for _, prof in pairs(char.professions or {}) do
    professions[#professions + 1] = string.format("%s (%s→%s) %s", tostring(prof.name), tostring(prof.line), tostring(prof.id), tostring(prof.skill))
  end
  table.sort(professions)
  local map, x, y
  if ns.Positions and ns.Positions.Here then map, x, y = ns.Positions.Here() end -- pas de « and » : il tronquerait les retours
  local pins = LibStub and LibStub("HereBeDragons-Pins-2.0", true)
  lines[#lines + 1] = string.format("lecture · talents : %s (%s) · métiers : %s · guilde : %s · position : %s · points de carte : %s · mort : %s",
    tostring((ns.TalentApi and ns.TalentApi()) or "aucune"),
    char.talents and char.talents.api and (char.talents.spells and "sorts" or "arbres") or "jamais lu",
    #professions > 0 and table.concat(professions, ", ") or "aucun",
    (IsInGuild and IsInGuild()) and "oui" or "non",
    map and string.format("carte %s%s", tostring(map), x and string.format(" (%.2f, %.2f)", x, y) or " sans coordonnées") or "illisible",
    pins and "bibliothèque chargée" or "bibliothèque absente",
    (ns.DeathSource and ns.DeathSource()) or "aucune mort cette session")
  -- Chaîne de victoire honorable du client, telle que lue pour détecter les kills de joueurs (Wanted), le dernier
  -- message reçu et ce qu'on en a tiré, le compteur de kills du client.
  lines[#lines + 1] = string.format("victoire honorable · chaîne : %s · motif : %s · %s",
    type(COMBATLOG_HONORGAIN) == "string" and COMBATLOG_HONORGAIN or "absente",
    (ns.Wanted and ns.Wanted.HonorPatterns and table.concat(ns.Wanted.HonorPatterns(), " | ")) or "aucun",
    (ns.Wanted and ns.Wanted.HonorSource and ns.Wanted.HonorSource()) or "rien lu")
  -- Annonce du kill à la guilde : le jeu a-t-il pris le « K » ou le « H », et en reçoit-on ?
  lines[#lines + 1] = "annonce des kills · " .. ((ns.Wanted and ns.Wanted.AnnounceSource and ns.Wanted.AnnounceSource()) or "rien")
  lines[#lines + 1] = "journal des kills · " .. ((ns.Wanted and ns.Wanted.KillLog and ns.Wanted.KillLog() ~= "" and ns.Wanted.KillLog()) or "vide")
  lines[#lines + 1] = "popups · " .. ((ns.UI and ns.UI.ToastSource and ns.UI.ToastSource()) or "rien")
  -- Récolte : le dernier sort lu (identifiant, nom, événement) et ce que le collecteur en a fait ; la pêche se
  -- diagnostique ainsi en jeu (sort non reconnu, ou butin hors fenêtre dans /mf trace).
  lines[#lines + 1] = "récolte · " .. ((ns.GatherSource and ns.GatherSource()) or "aucun sort de récolte lu cette session")
  local client = ""
  if type(GetBuildInfo) == "function" then
    local ok, version, build, _, toc = pcall(GetBuildInfo)
    if ok then client = string.format("client %s (%s, %s)", tostring(version), tostring(build), tostring(toc)) end
  end
  return lines, client
end

--- Note le diagnostic avec les erreurs : il part au site au prochain envoi (page « Tests en jeu »).
function ns.SaveDiagnostic()
  local lines, client = ns.DiagnosticLines()
  ns.Store.LogError("diagnostic", table.concat(lines, " | ") .. (client ~= "" and (" · " .. client) or ""))
  ns.Print(ns.L.DIAG_SAVED)
end

--- /mf api : le diagnostic dans le chat, et noté pour le site.
function ns.Diagnostic()
  for _, line in ipairs((ns.DiagnosticLines())) do ns.Print("%s", line) end
  ns.SaveDiagnostic()
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
  entry.class, entry.race = classToken, raceToken
  if (level or 0) > (entry.level or 0) then entry.level = level end -- jamais vers le bas (cf. Identity)
  entry.faction = UnitFactionGroup and UnitFactionGroup("player") or nil

  for _, def in ipairs(ns.collectors) do
    for event in pairs(def.events or {}) do registerEvent(event) end
    if def.onLogin then ns.Safe(def.name .. ".onLogin", def.onLogin, entry) end
  end
  ns.Journal.Rollover(entry, ns.now())
  ns.Safe("upgrade.login", ns.UpgradeOnLogin)
  C_Timer.After(3, ns.FullScan)
  C_Timer.NewTicker(60, function() ns.Safe("tick", ns.Tick) end)
  if ns.UI and ns.UI.OnLogin then ns.Safe("UI.OnLogin", ns.UI.OnLogin, entry) end
end

--- Vrai si `other` (« a.b.c ») est plus récente que `mine`. « dev » ou forme inconnue : jamais.
function ns.VersionNewer(other, mine)
  local function parts(v)
    local out = {}
    for n in tostring(v or ""):gmatch("%d+") do out[#out + 1] = tonumber(n) end
    return out
  end
  local a, b = parts(other), parts(mine)
  if #a == 0 or #b == 0 then return false end
  for i = 1, math.max(#a, #b) do
    local x, y = a[i] or 0, b[i] or 0
    if x ~= y then return x > y end
  end
  return false
end

-- Mise à jour : chaque guildien annonce sa version avec sa position. Quand UPGRADE_PEERS d'entre eux ont plus
-- récent que moi (un seul ne suffit pas : une version de développement en jeu ne dérange personne), une ligne de
-- chat tout de suite, puis le popup de rechargement dès qu'on est hors combat et hors instance (ReloadUI est
-- refusé en combat), une fois par version et par session.
--
-- L'addon ne voit pas le disque : il ne sait pas si le compagnon a déjà copié la nouvelle version. Il retient
-- donc, d'une session à l'autre (`db.upgradeTried`), qu'on a rechargé pour une version. Toujours en retard après
-- ce rechargement : il le dit une fois par session, repropose une seule fois après UPGRADE_RETRY (le compagnon
-- a pu arriver entre-temps), puis n'insiste plus pour cette version. Sans cela, le popup revenait à chaque
-- rechargement tant que les fichiers n'étaient pas là.
ns.upgrade = { seen = nil, asked = {}, peers = {} }

--- Le rechargement déjà tenté qui couvre cette version, s'il y en a un.
local function upgradeAttempt(version)
  local tried = ns.db and ns.db.upgradeTried
  if type(tried) == "table" and tried.version and not ns.VersionNewer(version, tried.version) then return tried end
  return nil
end

--- La version la plus haute qu'au moins UPGRADE_PEERS guildiens ont atteinte, si elle dépasse la mienne.
local function confirmedVersion()
  local versions = {}
  for _, version in pairs(ns.upgrade.peers) do versions[#versions + 1] = version end
  table.sort(versions, ns.VersionNewer)
  return versions[ns.Data.UPGRADE_PEERS]
end

function ns.TryUpgradePopup()
  local version = ns.upgrade.seen
  if not version or ns.upgrade.asked[version] then return end
  local tried = upgradeAttempt(version)
  if tried then
    if (tried.n or 1) >= ns.Data.UPGRADE_TRIES then return end
    if ns.now() - (tried.t or 0) < ns.Data.UPGRADE_RETRY then return end
  end
  if ns.InCombat() or (IsInInstance and IsInInstance()) then return end
  ns.upgrade.asked[version] = true
  if ns.UI and ns.UI.SuggestUpgrade then ns.UI.SuggestUpgrade(version) end
end

--- `guid` : le guildien qui annonce cette version (sans lui, la version compte pour un seul annonceur).
function ns.NoticeVersion(version, guid)
  if not ns.VersionNewer(version, ns.VERSION) then return end
  ns.upgrade.peers[guid or version] = version
  local confirmed = confirmedVersion()
  if not confirmed then return end
  if not ns.upgrade.seen or ns.VersionNewer(confirmed, ns.upgrade.seen) then
    ns.upgrade.seen = confirmed
    local line = upgradeAttempt(confirmed) and ns.L.UPGRADE_MISSING or ns.L.UPGRADE_CHAT
    ns.Print(line, confirmed, tostring(ns.VERSION))
  end
  ns.TryUpgradePopup()
end

--- « Recharger » du popup : on retient la tentative avant de recharger, le client écrit la base au passage.
function ns.UpgradeAccepted(version)
  version = version or ns.upgrade.seen
  if version and ns.db then
    local tried = ns.db.upgradeTried
    local count = (type(tried) == "table" and tried.version == version and tried.n or 0) + 1
    ns.db.upgradeTried = { version = version, n = count, t = ns.now() }
  end
  ReloadUI()
end

--- À la connexion : la version attendue est arrivée → la tentative est oubliée. Le jeu a été lancé avec un .toc
--- plus ancien que le code → il faudra le relancer pour qu'il relise la liste des fichiers de l'addon.
function ns.UpgradeOnLogin()
  local tried = ns.db and ns.db.upgradeTried
  if type(tried) ~= "table" or not tried.version or not ns.VersionNewer(tried.version, ns.VERSION) then
    if ns.db then ns.db.upgradeTried = nil end
  end
  if ns.TOC_VERSION and ns.VersionNewer(ns.VERSION, ns.TOC_VERSION) then
    ns.Print(ns.L.UPGRADE_RESTART, tostring(ns.VERSION), tostring(ns.TOC_VERSION))
  end
end

function ns.Tick()
  local entry = ns.char
  if not entry then return end
  local t = ns.now()
  ns.Journal.Rollover(entry, t)
  ns.TryUpgradePopup()
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
  elseif event == "ADDON_ACTION_FORBIDDEN" or event == "ADDON_ACTION_BLOCKED" then
    -- Le jeu a refusé un appel réservé à son interface : ce n'est pas une erreur Lua, on la note nous-mêmes
    -- (chat, /mf erreurs, et le site au prochain envoi) avec le nom de la fonction, pour savoir quoi corriger.
    local addon, func = ...
    if addon == ADDON then
      local last = ns.lastRisky
      local hint = last and string.format(" (dernier appel sensible : %s, il y a %d s)", last.name, ns.now() - last.t) or ""
      local what = string.format("%s : %s%s", event, tostring(func), hint)
      ns.Store.LogError("protected", what)
      ns.Print(ns.L.ACTION_BLOCKED, tostring(func))
    end
  else
    dispatch(event, ...)
  end
end)
frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("PLAYER_LOGOUT")
frame:RegisterEvent("ADDON_ACTION_FORBIDDEN")
frame:RegisterEvent("ADDON_ACTION_BLOCKED")
frame:RegisterEvent("PLAYER_REGEN_ENABLED")

SLASH_WOWFOREVERGUILDE1 = "/mf" -- Manuel Feralas, nom voté le 4 novembre 2026
SLASH_WOWFOREVERGUILDE2 = "/wfg" -- ancien alias, gardé pour les habitudes
SlashCmdList.WOWFOREVERGUILDE = function(raw)
  raw = raw or ""
  local msg = raw:lower():gsub("^%s+", "")
  if msg == "export" and ns.UI then ns.UI.ShowExport()
  elseif msg == "save" or msg == "reload" then ReloadUI()
  elseif msg == "qui" or msg == "who" then ns.RosterUI.Toggle()
  elseif msg == "wanted" then ns.WantedUI.Toggle()
  elseif (msg == "historique" or msg == "histo") and ns.UI then ns.UI.Toggle("history")
  elseif (msg == "collecte" or msg == "collect") and ns.UI then ns.UI.Toggle("collect")
  elseif (msg == "reglages" or msg == "réglages" or msg == "options") and ns.UI then ns.UI.Toggle("settings")
  elseif msg == "sos" then ns.Positions.SOS()
  elseif msg == "erreurs" or msg == "errors" then ns.PrintErrors()
  elseif msg == "api" then ns.Safe("diagnostic", ns.Diagnostic)
  elseif msg == "diag" and ns.UI then ns.UI.Toggle("diag")
  elseif (msg == "nouveautes" or msg == "nouveautés" or msg == "news") and ns.UI then ns.UI.Toggle("news")
  elseif msg == "trace" then
    ns.traceUntil = ns.now() + ns.Data.TRACE_SECONDS
    ns.Print(ns.L.TRACE_ON, ns.Data.TRACE_SECONDS)
  elseif msg:match("^lfg") then ns.Positions.SetLFG(raw:gsub("^%s*[Ll][Ff][Gg]", ""))
  elseif msg:match("^prime") then ns.Safe("wanted.rehearse", ns.Wanted.Rehearse, (raw:gsub("^%s*[Pp][Rr][Ii][Mm][Ee]", "")))
  elseif ns.UI then ns.UI.Toggle() end
end
