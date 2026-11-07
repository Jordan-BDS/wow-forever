-- Accès aux raids : quêtes d'accès marquées terminées (table Data.ATTUNEMENTS).
local ADDON, ns = ...

local function completed(questId)
  if C_QuestLog and C_QuestLog.IsQuestFlaggedCompleted then return C_QuestLog.IsQuestFlaggedCompleted(questId) end
  if IsQuestFlaggedCompleted then return IsQuestFlaggedCompleted(questId) end
  return nil
end

local function scan(char)
  local faction = char.faction
  local before = char.attunements or {}
  local after = {}
  for _, entry in ipairs(ns.Data.ATTUNEMENTS) do
    if entry.faction == "any" or entry.faction == faction then
      local done = completed(entry.quest)
      -- Un accès acquis ne se perd jamais : une lecture négative ou absente (drapeaux de quêtes pas encore reçus
      -- à la connexion, déconnexion) ne retire rien.
      local known = before[entry.key] == true
      if done ~= nil or known then
        after[entry.key] = after[entry.key] or known or done == true
        if done and not known and char.attunements_at then
          ns.Journal.Event(char, "attunement", { key = entry.key })
          ns.Print(ns.L.NEW_ATTUNEMENT, entry.key)
        end
      end
    end
  end
  char.attunements = after
  char.attunements_at = ns.now()
end

ns.RegisterCollector({
  name = "attunements",
  events = { QUEST_TURNED_IN = true },
  scanOn = { QUEST_TURNED_IN = true },
  scan = scan,
})
