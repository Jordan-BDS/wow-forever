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
      if done ~= nil then
        after[entry.key] = after[entry.key] or done
        if done and not before[entry.key] and char.attunements_at then
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
