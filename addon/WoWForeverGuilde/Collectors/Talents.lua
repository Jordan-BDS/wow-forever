-- Talents : rang par talent et arbre dominant. API à confirmer sur Forever (arbres Classic sur un client moderne) :
-- on essaie l'API Classic, puis on marque « indisponible » sans jamais planter.
local ADDON, ns = ...

local available = nil

local function scan(char)
  if GetNumTalentTabs and GetTalentInfo and GetNumTalents then
    local tabs, points, best, bestPoints = {}, {}, nil, -1
    for tab = 1, GetNumTalentTabs() do
      local spent = 0
      for index = 1, GetNumTalents(tab) do
        local _, _, _, _, rank = GetTalentInfo(tab, index)
        rank = ns.plain(rank) or 0
        if rank > 0 then
          points[tab .. "-" .. index] = rank
          spent = spent + rank
        end
      end
      tabs[#tabs + 1] = spent
      if spent > bestPoints then best, bestPoints = tab, spent end
    end
    char.talents = { tabs = ns.Json.array(tabs), points = points }
    char.spec_tab = bestPoints > 0 and best or nil
    char.talents_at = ns.now()
    available = true
    return
  end
  available = false
end

ns.RegisterCollector({
  name = "talents",
  events = { PLAYER_TALENT_UPDATE = true, CHARACTER_POINTS_CHANGED = true, SPELLS_CHANGED = true },
  scanOn = { PLAYER_TALENT_UPDATE = true, CHARACTER_POINTS_CHANGED = true },
  scan = scan,
  status = function(char)
    if available == false then return ns.L.NOT_AVAILABLE end
    return char.talents_at and string.format(ns.L.UP_TO_DATE, ns.UI.Ago(char.talents_at)) or ns.L.NEVER_READ
  end,
})
