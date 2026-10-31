-- PvP : victoires honorables à vie et rang (totaux du jeu) ; champs de bataille joués / gagnés comptés par l'addon.
local ADDON, ns = ...

local function scan(char)
  local pvp = char.pvp or {}
  if GetPVPLifetimeStats then
    local hk = ns.plain((GetPVPLifetimeStats()))
    pvp.hk_lifetime = hk
    -- Total tenu par le jeu, recopié dans les compteurs pour que le journal quotidien en garde la trace.
    if type(hk) == "number" then char.counters.hk = hk end
  end
  if UnitPVPRank then pvp.rank = ns.plain(UnitPVPRank("player")) end
  if UnitHonor and UnitHonorLevel then
    pvp.honor = ns.plain(UnitHonor("player"))
    pvp.honor_level = ns.plain(UnitHonorLevel("player"))
  end
  pvp.bg = pvp.bg or {}
  char.pvp = pvp
  char.pvp_at = ns.now()
end

local currentMap = nil
local counted = false

--- Sortie du champ de bataille : le prochain match (même sur la même carte) doit être compté.
local function leaveBattlefield()
  currentMap = nil
  counted = false
end

local function recordMatch(char, won)
  local map = currentMap or "unknown"
  char.pvp = char.pvp or {}
  char.pvp.bg = char.pvp.bg or {}
  local bucket = char.pvp.bg[map] or { played = 0, won = 0 }
  bucket.played = bucket.played + 1
  if won then bucket.won = bucket.won + 1 end
  char.pvp.bg[map] = bucket
  ns.Journal.Increment(char, "bg_played")
  if won then ns.Journal.Increment(char, "bg_won") end
  ns.Journal.Event(char, "bg", { map = map, won = won and true or false })
end

ns.RegisterCollector({
  name = "pvp",
  events = {
    PVP_MATCH_COMPLETE = true, UPDATE_BATTLEFIELD_STATUS = true, HONOR_XP_UPDATE = true, PLAYER_PVP_KILLS_CHANGED = true,
    PLAYER_ENTERING_WORLD = true,
  },
  scanOn = { HONOR_XP_UPDATE = true, PLAYER_PVP_KILLS_CHANGED = true },
  scan = scan,
  onEvent = function(char, event, ...)
    if event == "PLAYER_ENTERING_WORLD" then
      local inside, kind = IsInInstance()
      if not (inside and kind == "pvp") then leaveBattlefield() end
    elseif event == "UPDATE_BATTLEFIELD_STATUS" and GetMaxBattlefieldID and GetBattlefieldStatus then
      local active = false
      for i = 1, GetMaxBattlefieldID() do
        local status, mapName = GetBattlefieldStatus(i)
        if status == "active" then
          active = true
          if currentMap ~= mapName then counted = false end
          currentMap = mapName
          -- Fin de match détectée par l'écran des scores (vainqueur connu), si PVP_MATCH_COMPLETE n'existe pas.
          if not PVP_MATCH_COMPLETE_SUPPORTED and GetBattlefieldWinner then
            local winner = GetBattlefieldWinner()
            if winner ~= nil and not counted then
              counted = true
              local mine = UnitFactionGroup and UnitFactionGroup("player")
              local won = (winner == 0 and mine == "Horde") or (winner == 1 and mine == "Alliance")
              recordMatch(char, won)
            end
          end
        end
      end
      -- Plus aucun champ de bataille actif : on a quitté le BG.
      if not active then leaveBattlefield() end
    elseif event == "PVP_MATCH_COMPLETE" then
      PVP_MATCH_COMPLETE_SUPPORTED = true
      local winner = ...
      if not counted then
        counted = true
        local mine = UnitFactionGroup and UnitFactionGroup("player")
        local won = (winner == 0 and mine == "Horde") or (winner == 1 and mine == "Alliance")
        recordMatch(char, won)
      end
    end
  end,
  status = function(char)
    local pvp = char.pvp or {}
    if not char.pvp_at then return ns.L.NEVER_READ end
    return string.format("%s VH · %d BG", tostring(pvp.hk_lifetime or "?"), (char.counters and char.counters.bg_played) or 0)
  end,
})
