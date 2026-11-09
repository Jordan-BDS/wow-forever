-- Environnement WoW minimal pour exécuter l'addon hors du jeu (tests pytest via lupa).
-- Horloge pilotable depuis Python : _CLOCK.now. Événements : _FIRE(event, ...). Fenêtres : objets factices.
_CLOCK = { now = 1764000000 }
_CHAT = {}
_SENT = {}
_FRAMES = {}
_TIMERS = {}
_SOUNDS = {}

C_AddOns = { GetAddOnMetadata = function(addon, key) if key == "Version" then return _ADDON_VERSION or "0.0.0" end end }
-- Client de jeu : version, build, date, version d'interface (Forever = 16001) ; projet 1 = WoW.
_BUILD = { version = "1.60.1", build = "12345", date = "Oct 31 2026", toc = 16001 }
function GetBuildInfo() return _BUILD.version, _BUILD.build, _BUILD.date, _BUILD.toc end
WOW_PROJECT_ID = 1
function GetServerTime() return _CLOCK.now end
function time() return _CLOCK.now end
function date(fmt, ts) return os.date(fmt, ts or _CLOCK.now) end
function tinsert(t, v) table.insert(t, v) end
UISpecialFrames = {}
UIParent = { GetEffectiveScale = function() return 1 end }
NUM_CHAT_WINDOWS = 1
SlashCmdList = {}
StaticPopupDialogs = {}
LOCALIZED_CLASS_NAMES_MALE = { SHAMAN = "Chaman", MAGE = "Mage" }
-- Valeur « secrète » du client moderne : toute opération Lua dessus échoue, seul issecretvalue la reconnaît.
_SECRET = setmetatable({}, {
  __tostring = function() error("attempt to use a secret value") end,
  __concat = function() error("attempt to concatenate a secret value") end,
})
function issecretvalue(v) return v == _SECRET end
RAID_CLASS_COLORS = { SHAMAN = { r = 0, g = 0.44, b = 0.87, colorStr = "ff0070dd" }, MAGE = { r = 0.41, g = 0.8, b = 0.94, colorStr = "ff69ccf0" } }
SOUNDKIT = { RAID_WARNING = 8959 }
function PlaySound(id) table.insert(_SOUNDS, id) end
function StaticPopup_Show(which, text) _POPUP = { which = which, text = text } return { data = nil } end
function UIFrameFadeIn() end
function UIFrameFadeOut() end
function ReloadUI() _RELOADED = true end
function InCombatLockdown() return _COMBAT == true end
function UnitAffectingCombat() return _COMBAT == true end
function IsInInstance() return _INSTANCE ~= nil, _INSTANCE end
function GetInstanceInfo() return _INSTANCE_NAME or "", _INSTANCE or "none", 0, "", 5, 0, false, _INSTANCE_ID or 0 end
function IsInGroup() return _IN_GROUP == true end
function IsInRaid() return false end
function GetNumGroupMembers() return 0 end
_TARGET = nil -- { name = "Garrosh", class = "WARRIOR", player = true, hostile = true }
COMBATLOG_XPGAIN_FIRSTPERSON = "%s meurt, vous gagnez %d points d'expérience."
COMBATLOG_XPGAIN_FIRSTPERSON_GROUP = "%s meurt, vous gagnez %d points d'expérience. (+%d bonus de groupe)"
function UnitCanAttack(a, b) return b == "target" and _TARGET ~= nil and _TARGET.hostile == true end
function UnitExists(unit) return unit == "target" and _TARGET ~= nil end
function UnitIsInMyGuild() return false end

-- Personnage joué.
_PLAYER = { guid = "Player-1-000ABC01", name = "Thrall Fils-de-Durotan", realm = "Forever", class = { "Chaman", "SHAMAN" },
            race = { "Orc", "Orc" }, level = 60, faction = "Horde" }
function UnitGUID(unit) if unit == "player" then return _PLAYER.guid end end
function UnitName(unit) if unit == "target" then return _TARGET and _TARGET.name end return (_PLAYER.name:match("^(%S+)")), nil end
function UnitFullName(unit) return _PLAYER.name, _PLAYER.realm end
function GetRealmName() return _PLAYER.realm end
function UnitClass(unit) if unit == "target" then return _TARGET and _TARGET.class, _TARGET and _TARGET.class end return _PLAYER.class[1], _PLAYER.class[2] end
function UnitRace() return _PLAYER.race[1], _PLAYER.race[2] end
function UnitLevel() return _PLAYER.level end
function UnitFactionGroup() return _PLAYER.faction end
function GetZoneText() return _ZONE or "Forêt d'Elwynn" end
function GetSubZoneText() return _SUBZONE or "" end
function RequestTimePlayed() _FIRE("TIME_PLAYED_MSG", 123456, 1000) end
function ChatFrame_AddMessageEventFilter() end
function RequestRaidInfo() end

-- Équipement.
_GEAR = { [1] = "|cffa335ee|Hitem:16842:2583:0:0:0:0:0:0:60|h[Couronne]|h|r", [16] = "|Hitem:17182:0:0|h[Sulfuras]|h" }
function GetInventoryItemLink(unit, slot) return _GEAR[slot] end

-- Talents (API Classic).
_TALENTS = { tabs = 3, per_tab = 2, ranks = { ["1-1"] = 0, ["1-2"] = 0, ["2-1"] = 5, ["2-2"] = 3, ["3-1"] = 1, ["3-2"] = 0 } }
function GetNumTalentTabs() return _TALENTS.tabs end
function GetNumTalents(tab) return _TALENTS.per_tab end
-- Rangée et colonne comme le jeu les numérote (à partir de 1) : l'index 1 est en (1,1), l'index 2 en (1,2).
function GetTalentInfo(tab, index) return "Talent", "icon", 1, index, _TALENTS.ranks[tab .. "-" .. index] or 0, 5 end
-- Traits modernes (C_Traits) : actifs quand _TRAITS est posé et que l'API Classic est retirée par le test.
-- _TRAITS = { [spellId] = rang }.
_TRAITS = nil
C_ClassTalents = { GetActiveConfigID = function() return _TRAITS and 1 or nil end }
C_Traits = {
  GetConfigInfo = function(id) return _TRAITS and { treeIDs = { 10 } } or nil end,
  GetTreeNodes = function() local ids = {} for spell in pairs(_TRAITS or {}) do table.insert(ids, spell) end table.sort(ids) return ids end,
  GetNodeInfo = function(_, nodeID) return { activeRank = _TRAITS[nodeID], activeEntry = { entryID = nodeID } } end,
  GetEntryInfo = function(_, entryID) return { definitionID = entryID } end,
  GetDefinitionInfo = function(defID) return { spellID = defID } end,
}
function GetTalentTabInfo(tab) return ({ "Élémentaire", "Amélioration", "Restauration" })[tab], "icon", 0 end

-- Métiers.
_PROFESSIONS = { { name = "Minage", skill = 300, max = 300, line = 186 }, { name = "Alchimie", skill = 290, max = 300, line = 171 } }
-- Six emplacements (métier 1, métier 2, archéologie, pêche, cuisine, secourisme), avec des trous (nil) possibles.
_PROFESSION_SLOTS = { 1, 2 }
function GetProfessions() return unpack(_PROFESSION_SLOTS, 1, 6) end
function GetProfessionInfo(i) local p = _PROFESSIONS[i] if not p then return nil end return p.name, "icon", p.skill, p.max, 0, 0, p.line end
_OPEN_TRADESKILL = nil
-- Hiérarchie des lignes de compétence d'une base moderne : _SKILL_PARENTS[ligne d'extension] = ligne mère.
_SKILL_PARENTS = {}
_SKILL_INFO = {} -- compétence propre à une ligne : _SKILL_INFO[ligne] = { skillLevel, maxSkillLevel }
_OPEN_CHILD = nil
C_TradeSkillUI = {
  GetBaseProfessionInfo = function() return _OPEN_TRADESKILL end,
  GetChildProfessionInfo = function() return _OPEN_CHILD end,
  GetProfessionInfoBySkillLineID = function(line)
    local own = _SKILL_INFO[line] or {}
    return { professionID = line, parentProfessionID = _SKILL_PARENTS[line] or 0, skillLevel = own.skillLevel, maxSkillLevel = own.maxSkillLevel }
  end,
  IsTradeSkillLinked = function() return false end,
  GetAllRecipeIDs = function() return _OPEN_TRADESKILL and _OPEN_TRADESKILL.recipes or {} end,
  -- Fiche de recette : répond pour toute recette connue du client, fenêtre ouverte ou non ; nil pour un sort qui
  -- n'est pas une recette. _RECIPE_INFO[id] = apprise ?
  GetRecipeInfo = function(id)
    local learned = _RECIPE_INFO[id]
    if learned == nil then return nil end
    return { recipeID = id, learned = learned }
  end,
}
_RECIPE_INFO = { [17580] = true, [11448] = true, [99999] = false }
-- API Classic de la fenêtre de métier : liste mêlant en-têtes et recettes, sort dans le lien « enchant ».
-- _CLASSIC_TRADESKILL = { { name, type = "header" | "optimal" | …, link } }, nil = fenêtre fermée.
_CLASSIC_TRADESKILL = nil
function GetNumTradeSkills() return _CLASSIC_TRADESKILL and #_CLASSIC_TRADESKILL or 0 end
function GetTradeSkillInfo(i) local r = _CLASSIC_TRADESKILL and _CLASSIC_TRADESKILL[i] if not r then return nil end return r.name, r.type, 1, false end
function GetTradeSkillRecipeLink(i) local r = _CLASSIC_TRADESKILL and _CLASSIC_TRADESKILL[i] return r and r.link end
function GetTradeSkillLine() local t = _CLASSIC_TRADESKILL return t and t.name or "UNKNOWN", t and t.skill or 0, t and t.max or 0 end

-- Réputations.
C_Reputation = {
  GetNumFactions = function() return 2 end,
  GetFactionDataByIndex = function(i)
    if i == 1 then return { factionID = 609, name = "Cercle cénarien", reaction = 6, currentStanding = 9800 } end
    return { factionID = 0, isHeader = true }
  end,
}
_QUESTS_DONE = { [7848] = true }
C_QuestLog = { IsQuestFlaggedCompleted = function(id) return _QUESTS_DONE[id] == true end }
function GetNumSavedInstances() return 1 end
function GetSavedInstanceInfo() return "Cœur du Magma", 409, 300000, 9, true, false, 0, true, 40, "Normal", 10, 7 end
function GetPVPLifetimeStats() return 2340, 12 end
-- Champ de bataille : _BG = { status = "none"|"queued"|"confirm"|"active", map = "...", winner = nil|0|1 }.
_BG = { status = "none" }
function GetMaxBattlefieldID() return 1 end
function GetBattlefieldStatus(i) return _BG.status, _BG.map end
function GetBattlefieldWinner() return _BG.winner end
function UnitPVPRank() return 12 end
C_Spell = { GetSpellName = function(id) return "Sort" end }
_CLEU = nil
function CombatLogGetCurrentEventInfo() return unpack(_CLEU or {}) end
function JoinChannelByName() return 1 end
function GetChannelName(name) return 5, name end
function ChatFrame_RemoveChannel() end
function SendChatMessage(text, kind, lang, target) table.insert(_SENT, { text = text, kind = kind, target = target }) end

-- Messages addon, guilde, carte, groupe (partage de position).
_ADDON_SENT = {}
_PREFIXES = {}
C_ChatInfo = {
  RegisterAddonMessagePrefix = function(prefix) _PREFIXES[prefix] = true return true end,
  SendAddonMessage = function(prefix, text, kind, target) table.insert(_ADDON_SENT, { prefix = prefix, text = text, kind = kind, target = target }) return 0 end,
}
function IsInGuild() return _GUILD == true end
_MAP = { id = 1429, x = 0.5, y = 0.5 }
C_Map = {
  GetBestMapForUnit = function() return _MAP.id end,
  GetPlayerMapPosition = function(map) if _MAP.x then return { x = _MAP.x, y = _MAP.y } end end,
  GetMapInfo = function(id) return { mapID = id, name = "Forêt d'Elwynn" } end,
}
_INVITED = {}
_PARTY = {}
C_PartyInfo = { InviteUnit = function(name) table.insert(_INVITED, name) end }
function ChatFrame_OpenChat(text) _OPEN_CHAT = text end
function UnitIsGroupLeader() return _LEADER == true end
function UnitIsGroupAssistant() return false end
function UnitInParty(name) return _PARTY[name] == true end
function UnitInRaid() return nil end
function GetCursorPosition() return 100, 100 end
_ROSTER = {
  { name = "Thrall-Forever", level = 60, class = "SHAMAN", zone = "Forêt d'Elwynn", online = true, guid = "Player-1-000ABC01" },
  { name = "Jaina-Forever", level = 60, class = "MAGE", zone = "Forêt d'Elwynn", online = true, guid = "Player-1-00000JAI" },
  { name = "Uther-Forever", level = 58, class = "PALADIN", zone = "Marais des Chagrins", online = true, guid = "Player-1-00000UTH" },
  { name = "Absent-Forever", level = 12, class = "ROGUE", zone = "", online = false, guid = "Player-1-00000ABS" },
}
function GetNumGuildMembers() return #_ROSTER, 3 end
function GetGuildRosterInfo(i)
  local m = _ROSTER[i]
  if not m then return nil end
  return m.name, "Membre", 1, m.level, "Classe", m.zone, "", "", m.online, 0, m.class, 0, 0, false, false, 0, m.guid
end
C_GuildInfo = { GuildRoster = function() _ROSTER_REQUESTED = (_ROSTER_REQUESTED or 0) + 1 end }
_PLAYER_INFO = { ["Player-1-00000EVIL"] = { "Guerrier", "WARRIOR" } }
function GetPlayerInfoByGUID(guid) local p = _PLAYER_INFO[guid] if p then return p[1], p[2] end end
function UnitIsPlayer(unit) return unit == "target" and _TARGET ~= nil and _TARGET.player == true end
function StartDuel() end
function hooksecurefunc(name, fn)
  local orig = _G[name]
  _G[name] = function(...) local r = { orig(...) } fn(...) return unpack(r) end
end
ChatFrame1 = {}

-- Frames factices : enregistrent les événements et le script OnEvent.
_EVENT_HANDLERS = {}
local function newFrame(kind, name)
  local f = { kind = kind, name = name, events = {}, scripts = {}, shown = false, children = {}, texts = {} }
  function f:RegisterEvent(e) self.events[e] = true _EVENT_HANDLERS[self] = true end
  function f:UnregisterEvent(e) self.events[e] = nil end
  function f:SetScript(k, fn) self.scripts[k] = fn end
  function f:GetScript(k) return self.scripts[k] end
  function f:Show() self.shown = true if self.scripts.OnShow then self.scripts.OnShow(self) end end
  function f:Hide() self.shown = false end
  function f:IsShown() return self.shown end
  function f:CreateFontString() local s = newFrame("FontString") s.SetText = function(self, t) self.text = t end s.GetText = function(self) return self.text end return s end
  function f:CreateTexture() local s = newFrame("Texture") s.SetVertexColor = function(self, r, g, b) self.color = { r, g, b } end s.SetTexture = function(self, t) self.texture = t end return s end
  function f:IsMouseOver() return self.mouseOver == true end
  local noop = function() end
  for _, m in ipairs({ "SetSize", "SetPoint", "SetMovable", "EnableMouse", "RegisterForDrag", "SetFrameStrata", "SetBackdrop",
      "SetWidth", "SetJustifyH", "SetTextColor", "SetShadowOffset", "SetAlpha", "SetMultiLine", "SetAutoFocus", "SetFontObject",
      "SetScrollChild", "SetFocus", "HighlightText", "ClearFocus", "SetChecked", "StartMoving", "StopMovingOrSizing",
      "SetAllPoints", "SetTexture", "SetClampedToScreen", "ClearAllPoints", "SetHeight", "SetMaxLetters", "SetTextInsets",
      "SetTexCoord" }) do
    f[m] = noop
  end
  function f:SetAlpha(a) self.alpha = a end
  function f:SetText(t) self.text = t end
  function f:GetText() return self.text end
  function f:GetChecked() return self.checked end
  function f:SetEnabled(on) self.enabled = on end
  if name then _G[name] = f end
  table.insert(_FRAMES, f)
  return f
end
function CreateFrame(kind, name) return newFrame(kind, name) end
DEFAULT_CHAT_FRAME = { AddMessage = function(self, msg) table.insert(_CHAT, msg) end }
GameTooltip = newFrame("GameTooltip")
GameTooltip.lines = {}
function GameTooltip:SetOwner() end
function GameTooltip:ClearLines() self.lines = {} end
function GameTooltip:AddLine(text) table.insert(self.lines, text) end
function GameTooltip:AddDoubleLine(left, right) table.insert(self.lines, left .. "  " .. right) end

-- Minuteries : exécutées à la demande par _RUN_TIMERS().
C_Timer = {
  After = function(delay, fn) table.insert(_TIMERS, { at = _CLOCK.now + delay, fn = fn }) end,
  NewTicker = function(period, fn) local t = { period = period, fn = fn, at = _CLOCK.now + period, ticker = true } table.insert(_TIMERS, t) return t end,
  NewTimer = function(delay, fn) local t = { at = _CLOCK.now + delay, fn = fn } function t:Cancel() t.cancelled = true end table.insert(_TIMERS, t) return t end,
}
function _RUN_TIMERS()
  local due = _TIMERS
  _TIMERS = {}
  for _, t in ipairs(due) do
    if not t.cancelled then
      if t.at <= _CLOCK.now then
        t.fn()
        if t.ticker then t.at = _CLOCK.now + t.period table.insert(_TIMERS, t) end
      else
        table.insert(_TIMERS, t)
      end
    end
  end
end
function _ADVANCE(seconds) _CLOCK.now = _CLOCK.now + seconds _RUN_TIMERS() end

function _FIRE(event, ...)
  for frame in pairs(_EVENT_HANDLERS) do
    if frame.events[event] and frame.scripts.OnEvent then frame.scripts.OnEvent(frame, event, ...) end
  end
end

-- Chargement d'un fichier de l'addon comme le fait le client : chunk(addonName, ns).
_NS = {}
function _LOAD(path, source)
  local chunk, err = loadstring(source, "@" .. path)
  if not chunk then error(err) end
  return chunk("WoWForeverGuilde", _NS)
end
