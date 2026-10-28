-- Tables de référence, mises à jour avec les releases. Les identifiants viennent du client ; à vérifier sur Forever.
local ADDON, ns = ...

ns.Data = {}

-- Emplacements d'équipement (identifiants d'inventaire → clé envoyée au site).
ns.Data.SLOTS = {
  [1] = "head", [2] = "neck", [3] = "shoulder", [15] = "back", [5] = "chest", [4] = "shirt", [19] = "tabard",
  [9] = "wrist", [10] = "hands", [6] = "waist", [7] = "legs", [8] = "feet", [11] = "finger1", [12] = "finger2",
  [13] = "trinket1", [14] = "trinket2", [16] = "mainhand", [17] = "offhand", [18] = "ranged",
}

-- Quêtes d'accès aux raids (identifiants vanilla ; à confirmer sur Forever). La faction est réglée dans l'addon
-- selon UnitFactionGroup ; "any" vaut pour les deux.
ns.Data.ATTUNEMENTS = {
  { key = "molten-core", quest = 7848, faction = "any" },
  { key = "onyxia", quest = 6502, faction = "Alliance" },
  { key = "onyxia", quest = 6602, faction = "Horde" },
  { key = "blackwing-lair", quest = 7761, faction = "any" },
}

-- Dernier boss de chaque instance (identifiant de rencontre → clé d'instance) : un kill = instance terminée.
-- Raids vanilla d'après les identifiants Classic Era ; donjons à compléter à la sortie (point ouvert).
ns.Data.FINAL_BOSSES = {
  [672] = { instance = "molten-core", raid = true },
  [1084] = { instance = "onyxia", raid = true },
  [617] = { instance = "blackwing-lair", raid = true },
  [796] = { instance = "zul-gurub", raid = true },
  [723] = { instance = "ruins-of-ahnqiraj", raid = true },
  [717] = { instance = "temple-of-ahnqiraj", raid = true },
  [1114] = { instance = "naxxramas", raid = true },
}

-- Sorts de récolte (identifiant → ressource). Tous les rangs vanilla.
ns.Data.GATHERING = {}
for _, id in ipairs({ 2575, 2576, 3564, 10248, 29354 }) do ns.Data.GATHERING[id] = "mining" end
for _, id in ipairs({ 2366, 2368, 3570, 11993, 28695 }) do ns.Data.GATHERING[id] = "herbalism" end
for _, id in ipairs({ 8613, 8617, 8618, 10768, 32678 }) do ns.Data.GATHERING[id] = "skinning" end
for _, id in ipairs({ 7620, 7731, 7732, 18248, 33095 }) do ns.Data.GATHERING[id] = "fishing" end
-- Repli par nom de sort, si les identifiants changent sur Forever.
ns.Data.GATHERING_NAMES = {
  ["Mining"] = "mining", ["Minage"] = "mining",
  ["Herb Gathering"] = "herbalism", ["Cueillette"] = "herbalism",
  ["Skinning"] = "skinning", ["Dépeçage"] = "skinning",
  ["Fishing"] = "fishing", ["Pêche"] = "fishing",
}

-- Dégâts d'environnement (journal de combat) → clé de traduction.
ns.Data.ENVIRONMENTAL = {
  Falling = "ENV_FALLING", Drowning = "ENV_DROWNING", Fatigue = "ENV_FATIGUE",
  Fire = "ENV_FIRE", Lava = "ENV_LAVA", Slime = "ENV_SLIME",
}

-- Canal caché des annonces de mort.
ns.Data.DEATH_CHANNEL = "wfgdeaths"
ns.Data.DEATH_CHANNEL_PASSWORD = "forever"
ns.Data.DEATH_PREFIX = "WFG\tDEATH\t1\t"

-- Bornes.
ns.Data.JOURNAL_DAYS = 60
ns.Data.MAX_EVENTS = 500
ns.Data.MAX_ERRORS = 50
ns.Data.RELOAD_REMINDER_SECONDS = 3 * 3600
ns.Data.GATHERING_WINDOW = 3
