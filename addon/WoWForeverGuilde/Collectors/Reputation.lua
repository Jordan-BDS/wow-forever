-- Réputations : faction → valeur et palier.
local ADDON, ns = ...

local function scan(char)
  local reputations = {}
  if C_Reputation and C_Reputation.GetNumFactions and C_Reputation.GetFactionDataByIndex then
    for i = 1, C_Reputation.GetNumFactions() do
      local data = C_Reputation.GetFactionDataByIndex(i)
      if data and data.factionID and not data.isHeader then
        reputations[tostring(data.factionID)] = { v = ns.plain(data.currentStanding), r = ns.plain(data.reaction) }
      end
    end
  elseif GetNumFactions and GetFactionInfo then
    for i = 1, GetNumFactions() do
      local _, _, standing, _, _, value, _, _, isHeader, _, _, _, _, factionID = GetFactionInfo(i)
      if factionID and not isHeader then reputations[tostring(factionID)] = { v = value, r = standing } end
    end
  else
    return
  end
  char.reputations = reputations
  char.reputations_at = ns.now()
end

ns.RegisterCollector({
  name = "reputation",
  events = { UPDATE_FACTION = true },
  scanOn = { UPDATE_FACTION = true },
  scan = scan,
})
