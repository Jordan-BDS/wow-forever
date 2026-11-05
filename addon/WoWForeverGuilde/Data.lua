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
  [1121] = { instance = "naxxramas", raid = true },
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

-- Annonces de mort et positions : messages addon sur le canal de guilde (le client moderne interdit les canaux aux addons).
ns.Data.DEATH_PREFIX = "D\t1\t" -- message addon de mort (préfixe WFG, canal de guilde)

-- Partage de position (messages addon, préfixe enregistré auprès du client).
ns.Data.ADDON_PREFIX = "WFG"
ns.Data.POSITION_TICK = 10 -- s entre deux lectures de la position
ns.Data.POSITION_HEARTBEAT = 60 -- s : envoi même immobile
ns.Data.POSITION_TTL = 180 -- s sans nouvelle : le membre disparaît de la carte
ns.Data.POSITION_MOVE_THRESHOLD = 0.005 -- fraction de la carte : en dessous, on ne renvoie pas
ns.Data.POSITION_STACK = 0.01 -- fraction de la carte : points considérés superposés (infobulle et menu groupés)
ns.Data.GANK_COOLDOWN = 60 -- s entre deux appels à l'aide
ns.Data.ALERT_TTL = 120 -- s d'anneau rouge et de mention « attaqué » après un appel
ns.Data.ROSTER_REFRESH = 2 -- s de regroupement des rafraîchissements de la liste

-- Bornes.
-- Icône de la guilde : le portrait de Samwise Didier, l'icône bouche-trou « Temp » des clients Classic (celle de
-- Forever est le logo WoW), embarquée dans l'addon (Samwise.blp, 64×64).
ns.Data.ICON = "Interface\\AddOns\\WoWForeverGuilde\\Samwise"
ns.Data.JOURNAL_DAYS = 60
ns.Data.MAX_EVENTS = 500
ns.Data.MAX_ERRORS = 50
ns.Data.RELOAD_REMINDER_SECONDS = 3 * 3600
ns.Data.GATHERING_WINDOW = 3
ns.Data.MAX_MOBS = 500 -- créatures distinctes gardées par personnage (clé = nom affiché)
