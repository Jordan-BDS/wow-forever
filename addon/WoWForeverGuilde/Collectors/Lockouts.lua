-- Verrous d'instance en cours : réinitialisation et boss tombés.
local ADDON, ns = ...

local function scan(char)
  if not (GetNumSavedInstances and GetSavedInstanceInfo) then return end
  local lockouts = {}
  local t = ns.now()
  for i = 1, GetNumSavedInstances() do
    local name, id, reset, _, locked, extended, _, isRaid, maxPlayers, _, numEncounters, progress = GetSavedInstanceInfo(i)
    if (locked or extended) and reset and reset > 0 then
      lockouts[#lockouts + 1] = {
        name = name, id = id, reset_at = t + reset, raid = isRaid and true or false, size = maxPlayers,
        bosses = numEncounters, killed = progress,
      }
    end
  end
  char.lockouts = lockouts
  char.lockouts_at = t
end

ns.RegisterCollector({
  name = "lockouts",
  events = { UPDATE_INSTANCE_INFO = true, BOSS_KILL = true },
  scanOn = { UPDATE_INSTANCE_INFO = true },
  scan = scan,
  onLogin = function() if RequestRaidInfo then RequestRaidInfo() end end,
  onEvent = function(char, event) if event == "BOSS_KILL" and RequestRaidInfo then RequestRaidInfo() end end,
})
