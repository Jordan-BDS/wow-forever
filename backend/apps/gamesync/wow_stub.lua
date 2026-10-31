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
UIParent = {}
NUM_CHAT_WINDOWS = 1
SlashCmdList = {}
StaticPopupDialogs = {}
RAID_CLASS_COLORS = { SHAMAN = { colorStr = "ff0070dd" } }
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
function IsInGroup() return false end
function IsInRaid() return false end
function GetNumGroupMembers() return 0 end
function UnitExists() return false end
function UnitIsInMyGuild() return false end

-- Personnage joué.
_PLAYER = { guid = "Player-1-000ABC01", name = "Thrall Fils-de-Durotan", realm = "Forever", class = { "Chaman", "SHAMAN" },
            race = { "Orc", "Orc" }, level = 60, faction = "Horde" }
function UnitGUID(unit) if unit == "player" then return _PLAYER.guid end end
function UnitName(unit) return (_PLAYER.name:match("^(%S+)")), nil end
function UnitFullName(unit) return _PLAYER.name, _PLAYER.realm end
function GetRealmName() return _PLAYER.realm end
function UnitClass() return _PLAYER.class[1], _PLAYER.class[2] end
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
function GetTalentInfo(tab, index) return "Talent", "icon", 1, 1, _TALENTS.ranks[tab .. "-" .. index] or 0, 5 end

-- Métiers.
_PROFESSIONS = { { name = "Minage", skill = 300, max = 300, line = 186 }, { name = "Alchimie", skill = 290, max = 300, line = 171 } }
-- Six emplacements (métier 1, métier 2, archéologie, pêche, cuisine, secourisme), avec des trous (nil) possibles.
_PROFESSION_SLOTS = { 1, 2 }
function GetProfessions() return unpack(_PROFESSION_SLOTS, 1, 6) end
function GetProfessionInfo(i) local p = _PROFESSIONS[i] if not p then return nil end return p.name, "icon", p.skill, p.max, 0, 0, p.line end
_OPEN_TRADESKILL = nil
C_TradeSkillUI = {
  GetBaseProfessionInfo = function() return _OPEN_TRADESKILL end,
  IsTradeSkillLinked = function() return false end,
  GetAllRecipeIDs = function() return _OPEN_TRADESKILL and _OPEN_TRADESKILL.recipes or {} end,
  GetRecipeInfo = function(id) return { recipeID = id, learned = id ~= 99999 } end,
}

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
  local noop = function() end
  for _, m in ipairs({ "SetSize", "SetPoint", "SetMovable", "EnableMouse", "RegisterForDrag", "SetFrameStrata", "SetBackdrop",
      "SetWidth", "SetJustifyH", "SetTextColor", "SetShadowOffset", "SetAlpha", "SetMultiLine", "SetAutoFocus", "SetFontObject",
      "SetScrollChild", "SetFocus", "HighlightText", "ClearFocus", "SetChecked", "StartMoving", "StopMovingOrSizing" }) do
    f[m] = noop
  end
  function f:SetText(t) self.text = t end
  function f:GetText() return self.text end
  function f:GetChecked() return self.checked end
  if name then _G[name] = f end
  table.insert(_FRAMES, f)
  return f
end
function CreateFrame(kind, name) return newFrame(kind, name) end
DEFAULT_CHAT_FRAME = { AddMessage = function(self, msg) table.insert(_CHAT, msg) end }

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
