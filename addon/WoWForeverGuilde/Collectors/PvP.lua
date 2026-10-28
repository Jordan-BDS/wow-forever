-- PvP : victoires honorables à vie et rang (totaux du jeu) ; champs de bataille joués / gagnés comptés par l'addon.
local ADDON, ns = ...

local function scan(char)
  local pvp = char.pvp or {}
  if GetPVPLifetimeStats then
    local hk = GetPVPLifetimeStats()
    pvp.hk_lifetime = ns.plain(hk)
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
  },
  scanOn = { HONOR_XP_UPDATE = true, PLAYER_PVP_KILLS_CHANGED = true },
  scan = scan,
  onEvent = function(char, event, ...)
    if event == "UPDATE_BATTLEFIELD_STATUS" and GetMaxBattlefieldID and GetBattlefieldStatus then
      for i = 1, GetMaxBattlefieldID() do
        local status, mapName = GetBattlefieldStatus(i)
        if status == "active" then
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
