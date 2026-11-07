-- Récolte (sort de récolte puis butin dans la fenêtre qui suit : 10 s, 30 s pour la pêche dont le bouchon met du
-- temps à mordre ; fermée une seconde après la fenêtre de butin pour ne pas compter le butin d'un monstre tué
-- juste après) et artisanat (sort d'une recette connue).
local ADDON, ns = ...

local armed = nil -- { kind, until_t } : récolte en cours
local lastCraft = nil -- { id, t } : dernière fabrication comptée, pour ne pas la compter deux fois

local function lootFromMessage(msg)
  local itemId = msg:match("item:(%d+)")
  if not itemId then return nil end
  local qty = msg:match("x(%d+)%.?$") or msg:match("x(%d+)|r") or "1"
  return tonumber(itemId), tonumber(qty) or 1
end
ns.LootFromMessage = lootFromMessage

--- Une fabrication est vue deux fois sur une base moderne : le sort réussi, puis le résultat de fabrication. On ne
--- compte que la première des deux (même recette dans la seconde).
local function countCraft(char, spellId)
  local now = ns.now()
  if lastCraft and lastCraft.id == spellId and now - lastCraft.t < ns.Data.CRAFT_DEDUPE then return end
  lastCraft = { id = spellId, t = now }
  ns.Journal.Increment(char, "crafted_total")
  ns.Journal.IncrementIn(char, "crafted", spellId)
end

ns.RegisterCollector({
  name = "gathering",
  events = {
    UNIT_SPELLCAST_SUCCEEDED = true, CHAT_MSG_LOOT = true, LOOT_CLOSED = true,
    TRADE_SKILL_ITEM_CRAFTED_RESULT = true, -- base moderne : un événement par objet fabriqué, avec la recette
  },
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
        local window = kind == "fishing" and ns.Data.FISHING_WINDOW or ns.Data.GATHERING_WINDOW
        armed = { kind = kind, until_t = ns.now() + window }
      elseif ns.IsRecipe(spellId) then
        countCraft(char, spellId)
      end
    elseif event == "TRADE_SKILL_ITEM_CRAFTED_RESULT" then
      local result = ...
      local recipeId = type(result) == "table" and ns.plain(result.recipeID)
      if type(recipeId) == "number" then
        ns.knownRecipes = ns.knownRecipes or {}
        ns.knownRecipes[recipeId] = true
        countCraft(char, recipeId)
      end
    elseif event == "LOOT_CLOSED" then
      -- La fenêtre de butin se referme : la récolte est finie, le message de butin peut encore suivre d'un instant.
      if armed then armed.until_t = math.min(armed.until_t, ns.now() + ns.Data.LOOT_CLOSED_GRACE) end
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
