-- Récolte (sort de récolte puis butin dans les 3 s) et artisanat (sort d'une recette connue).
local ADDON, ns = ...

local armed = nil

local function lootFromMessage(msg)
  local itemId = msg:match("item:(%d+)")
  if not itemId then return nil end
  local qty = msg:match("x(%d+)%.?$") or msg:match("x(%d+)|r") or "1"
  return tonumber(itemId), tonumber(qty) or 1
end
ns.LootFromMessage = lootFromMessage

ns.RegisterCollector({
  name = "gathering",
  events = { UNIT_SPELLCAST_SUCCEEDED = true, CHAT_MSG_LOOT = true },
  onEvent = function(char, event, ...)
    if event == "UNIT_SPELLCAST_SUCCEEDED" then
      local unit, _, spellId = ...
      if unit ~= "player" then return end
      spellId = ns.plain(spellId)
      local kind = spellId and ns.Data.GATHERING[spellId]
      if not kind and spellId and C_Spell and C_Spell.GetSpellName then
        kind = ns.Data.GATHERING_NAMES[ns.plain(C_Spell.GetSpellName(spellId)) or ""]
      end
      if kind then
        armed = { kind = kind, until_t = ns.now() + ns.Data.GATHERING_WINDOW }
      elseif spellId and ns.knownRecipes and ns.knownRecipes[spellId] then
        ns.Journal.Increment(char, "crafted_total")
        ns.Journal.IncrementIn(char, "crafted", spellId)
      end
    elseif event == "CHAT_MSG_LOOT" then
      local msg, _, _, _, playerName = ...
      msg = ns.plain(msg)
      if not armed or type(msg) ~= "string" then return end
      if ns.now() > armed.until_t then armed = nil return end
      -- Seulement notre propre butin : le message « Vous recevez » n'a pas de nom de joueur, ou c'est le nôtre.
      local me = UnitName("player")
      if playerName and playerName ~= "" and playerName ~= me and not playerName:find("^" .. me .. "%-") then return end
      local itemId, qty = lootFromMessage(msg)
      if itemId then
        ns.Journal.IncrementIn(char, "gathering", armed.kind, qty)
        ns.Journal.IncrementIn(char, "gathered_items", itemId, qty)
      end
    end
  end,
  status = function(char)
    local g = (char.counters and char.counters.gathering) or {}
    return string.format("%d minerais · %d herbes · %d peaux · %d poissons · %d objets fabriqués",
      g.mining or 0, g.herbalism or 0, g.skinning or 0, g.fishing or 0, (char.counters and char.counters.crafted_total) or 0)
  end,
})
