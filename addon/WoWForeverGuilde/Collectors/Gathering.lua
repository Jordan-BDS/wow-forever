-- Récolte (sort de récolte puis butin dans la fenêtre qui suit : 10 s, 30 s pour la pêche dont le bouchon met du
-- temps à mordre ; fermée une seconde après la fenêtre de butin pour ne pas compter le butin d'un monstre tué
-- juste après) et artisanat (sort d'une recette connue).
-- Pêche (0.6.1) : le sort est canalisé, donc lu aussi à UNIT_SPELLCAST_CHANNEL_START (SUCCEEDED peut manquer ou
-- arriver autrement selon le client) ; la fin de canalisation (le bouchon cliqué) rouvre 10 s pour le butin, même
-- si la touche est tardive. Le sort est reconnu par son identifiant, sinon par son nom (C_Spell.GetSpellName ou
-- GetSpellInfo), exact ou approché (« Pêche », « Fishing »…). Le dernier sort lu et ce qu'on en a fait sont montrés
-- par /mf api et tracés par /mf trace, pour diagnostiquer en jeu.
local ADDON, ns = ...

local armed = nil -- { kind, until_t } : récolte en cours
local lastCraft = nil -- { id, t } : dernière fabrication comptée, pour ne pas la compter deux fois
local lastGather = nil -- { id, name, kind, event, t } : dernier sort lu, pour /mf api

local function lootFromMessage(msg)
  local itemId = msg:match("item:(%d+)")
  if not itemId then return nil end
  local qty = msg:match("x(%d+)%.?$") or msg:match("x(%d+)|r") or "1"
  return tonumber(itemId), tonumber(qty) or 1
end
ns.LootFromMessage = lootFromMessage

--- Nom d'un sort, par l'API moderne ou Classic ; "" si aucune ne répond.
local function spellName(spellId)
  if C_Spell and C_Spell.GetSpellName then
    local ok, name = pcall(C_Spell.GetSpellName, spellId)
    name = ok and ns.plain(name) or nil
    if type(name) == "string" and name ~= "" then return name end
  end
  if GetSpellInfo then
    local ok, name = pcall(GetSpellInfo, spellId)
    name = ok and ns.plain(name) or nil
    if type(name) == "string" and name ~= "" then return name end
  end
  return ""
end

-- Fragments de nom reconnus quand ni l'identifiant ni le nom exact ne sont connus (Forever peut renommer ou ranger).
local NAME_HINTS = {
  { "pêche", "fishing" }, { "minage", "mining" }, { "cueillette", "herb" }, { "dépeçage", "skinning" },
}
local HINT_KINDS = { "fishing", "mining", "herbalism", "skinning" }

--- Ressource d'un sort de récolte (mining, herbalism, skinning, fishing) et son nom ; nil si ce n'en est pas un.
local function gatheringKind(spellId)
  local kind = spellId and ns.Data.GATHERING[spellId]
  local name = spellName(spellId)
  if not kind and name ~= "" then
    kind = ns.Data.GATHERING_NAMES[name]
    if not kind then
      -- Minuscules ASCII seulement : string.lower selon la locale peut abîmer les octets UTF-8 (« ê »).
      local lower = (name:gsub("[A-Z]", function(c) return string.char(c:byte() + 32) end))
      for i, hints in ipairs(NAME_HINTS) do
        for _, hint in ipairs(hints) do
          if lower:find(hint, 1, true) then kind = HINT_KINDS[i] end
        end
      end
    end
  end
  return kind, name
end
ns.GatheringKind = gatheringKind

local function arm(kind)
  local window = kind == "fishing" and ns.Data.FISHING_WINDOW or ns.Data.GATHERING_WINDOW
  armed = { kind = kind, until_t = ns.now() + window }
  ns.Trace("récolte : %s armée %d s", kind, window)
end

--- Pour /mf api : le dernier sort lu par le collecteur et ce qu'il en a fait.
function ns.GatherSource()
  if not lastGather then return nil end
  return string.format("dernier sort %s « %s » (%s) → %s, il y a %d s", tostring(lastGather.id), lastGather.name ~= "" and lastGather.name or "sans nom",
    lastGather.event, lastGather.kind or "pas une récolte", ns.now() - lastGather.t)
end

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
    UNIT_SPELLCAST_SUCCEEDED = true, UNIT_SPELLCAST_CHANNEL_START = true, UNIT_SPELLCAST_CHANNEL_STOP = true,
    CHAT_MSG_LOOT = true, LOOT_CLOSED = true,
    TRADE_SKILL_ITEM_CRAFTED_RESULT = true, -- base moderne : un événement par objet fabriqué, avec la recette
  },
  onEvent = function(char, event, ...)
    if event == "UNIT_SPELLCAST_SUCCEEDED" or event == "UNIT_SPELLCAST_CHANNEL_START" then
      local unit, _, spellId = ...
      if unit ~= "player" then return end
      spellId = ns.plain(spellId)
      local kind, name = gatheringKind(spellId)
      lastGather = { id = spellId, name = name, kind = kind, event = event, t = ns.now() }
      if kind then
        -- Canalisation déjà armée par SUCCEEDED (ou l'inverse) : on ne raccourcit pas la fenêtre en cours.
        if not (armed and armed.kind == kind and armed.until_t > ns.now()) then arm(kind) end
      elseif event == "UNIT_SPELLCAST_SUCCEEDED" and ns.IsRecipe(spellId) then
        countCraft(char, spellId)
      end
    elseif event == "UNIT_SPELLCAST_CHANNEL_STOP" then
      local unit, _, spellId = ...
      if unit ~= "player" or not armed then return end
      -- Fin de la canalisation de pêche (bouchon cliqué) : le butin suit, même si la touche était tardive.
      local kind = gatheringKind(ns.plain(spellId))
      if kind == "fishing" and armed.kind == "fishing" then
        armed.until_t = math.max(armed.until_t, ns.now() + ns.Data.GATHERING_WINDOW)
        ns.Trace("récolte : canalisation de pêche finie, butin attendu %d s", ns.Data.GATHERING_WINDOW)
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
      if type(msg) ~= "string" then return end
      if not armed then
        ns.Trace("butin hors récolte : %s", msg:sub(1, 60))
        return
      end
      if ns.now() > armed.until_t then
        ns.Trace("butin %d s après la fin de la fenêtre de %s : non compté", ns.now() - armed.until_t, armed.kind)
        armed = nil
        return
      end
      -- Seulement notre propre butin : le message « Vous recevez » n'a pas de nom de joueur, ou c'est le nôtre.
      local me = UnitName("player")
      if playerName and playerName ~= "" and playerName ~= me and not playerName:find("^" .. me .. "%-") then return end
      local itemId, qty = lootFromMessage(msg)
      if itemId then
        ns.Journal.IncrementIn(char, "gathering", armed.kind, qty)
        ns.Journal.IncrementIn(char, "gathered_items", itemId, qty)
        ns.Trace("récolte : objet %d ×%d → %s", itemId, qty, armed.kind)
      end
    end
  end,
  status = function(char)
    local g = (char.counters and char.counters.gathering) or {}
    return string.format("%d minerais · %d herbes · %d peaux · %d poissons · %d objets fabriqués",
      g.mining or 0, g.herbalism or 0, g.skinning or 0, g.fishing or 0, (char.counters and char.counters.crafted_total) or 0)
  end,
})
