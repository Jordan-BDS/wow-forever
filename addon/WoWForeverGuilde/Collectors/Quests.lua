-- Quêtes rendues : simple compteur, les quêtes d'accès sont suivies à part.
local ADDON, ns = ...

ns.RegisterCollector({
  name = "quests",
  events = { QUEST_TURNED_IN = true },
  onEvent = function(char, event, questId)
    ns.Journal.Increment(char, "quests")
  end,
})
