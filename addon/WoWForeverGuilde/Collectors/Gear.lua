-- Équipement porté : identifiant d'objet et d'enchantement par emplacement, lus depuis le lien d'objet.
local ADDON, ns = ...

local function scan(char)
  local gear = {}
  for slotId, key in pairs(ns.Data.SLOTS) do
    local link = ns.plain(GetInventoryItemLink("player", slotId))
    if type(link) == "string" then
      local itemId, enchantId = link:match("item:(%d+):(%d*)")
      if itemId then
        local piece = { id = tonumber(itemId) }
        if enchantId and enchantId ~= "" and enchantId ~= "0" then piece.ench = tonumber(enchantId) end
        gear[key] = piece
      end
    end
  end
  char.gear = gear
  char.gear_at = ns.now()
end

ns.RegisterCollector({
  name = "gear",
  events = { PLAYER_EQUIPMENT_CHANGED = true },
  scanOn = { PLAYER_EQUIPMENT_CHANGED = true },
  scan = scan,
})
