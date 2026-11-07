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
-- Identifiants lus dans la table DungeonEncounter du client Forever (wago.tools, build 1.60.1.70862, 7 novembre 2026) ;
-- une instance à plusieurs ailes compte une fois par aile. Les donjons inédits de Forever prennent le dernier boss dans
-- l'ordre du client, à confirmer en jeu.
ns.Data.FINAL_BOSSES = {}
local function finalBosses(instance, raid, ids)
  for _, id in ipairs(ids) do ns.Data.FINAL_BOSSES[id] = { instance = instance, raid = raid } end
end
-- Raids.
finalBosses("onyxia", true, { 1084 }) -- Onyxia
finalBosses("molten-core", true, { 672 }) -- Ragnaros
finalBosses("blackwing-lair", true, { 617 }) -- Nefarian
finalBosses("zul-gurub", true, { 793 }) -- Hakkar
finalBosses("ruins-of-ahn-qiraj", true, { 723 }) -- Ossirian
finalBosses("temple-of-ahn-qiraj", true, { 717 }) -- C'Thun
finalBosses("naxxramas", true, { 1114 }) -- Kel'Thuzad
finalBosses("upper-blackrock-spire", true, { 3069 }) -- Général Drakkisath
-- Donjons vanilla.
finalBosses("ragefire-chasm", false, { 2735 }) -- Bazzalan
finalBosses("deadmines", false, { 2747 }) -- Edwin Van Cleef
finalBosses("wailing-caverns", false, { 592 }) -- Mutanus le Dévoreur
finalBosses("shadowfang-keep", false, { 2755 }) -- Archimage Arugal
finalBosses("blackfathom-deeps", false, { 2910, 2767, 2891 }) -- Aku'mai (trois variantes dans le client)
finalBosses("stockade", false, { 2760 }) -- Bazil Thredd
finalBosses("gnomeregan", false, { 2772, 2940 }) -- Mekgénieur Thermojoint (deux variantes)
finalBosses("razorfen-kraul", false, { 2778 }) -- Charlga Trancheflanc
finalBosses("scarlet-monastery", false, { 2779, 447, 448, 450 }) -- Thalnos (cimetière), Doan (bibliothèque), Herod (armurerie), Blanchetête (cathédrale)
finalBosses("razorfen-downs", false, { 2785 }) -- Amnennar le Porte-froid
finalBosses("uldaman", false, { 554 }) -- Archaedas
finalBosses("zul-farrak", false, { 600 }) -- Chef Ukorz Crinsable
finalBosses("maraudon", false, { 429 }) -- Princesse Theradras
finalBosses("sunken-temple", false, { 3584, 493, 2959 }) -- Ombre d'Eranikus (trois variantes)
finalBosses("blackrock-depths", false, { 2790 }) -- Empereur Dagran Thaurissan
finalBosses("lower-blackrock-spire", false, { 275 }) -- Seigneur Wyrmthalak
finalBosses("dire-maul", false, { 346, 361, 368 }) -- Alzzin (est), Prince Tortheldrin (ouest), Roi Gordok (nord)
finalBosses("scholomance", false, { 2801 }) -- Sombre maître Gandling
finalBosses("stratholme", false, { 478, 484 }) -- Balnazzar (côté vivant), Baron Vaillefendre (côté mort)
-- Donjons propres à Forever (dernier boss selon l'ordre du client).
finalBosses("demon-fall-canyon", false, { 3080 }) -- Azgaloth
finalBosses("karazhan-crypts", false, { 3172 }) -- Barian Maryla
finalBosses("city-of-dalaran", false, { 3303 }) -- Shade of the Archmage
finalBosses("drowned-city", false, { 3479 }) -- Min'loth the Serpent
finalBosses("blackmaw-hold", false, { 3336 }) -- Unbound Spirit
finalBosses("alcaz-prison", false, { 3409 }) -- Blazeroar
finalBosses("excavation-site-wetlands", false, { 3482 }) -- Relic Guardian
finalBosses("ruins-of-lordaeron", false, { 3354 }) -- Rath'mael
finalBosses("shapers-terrace", false, { 3502 }) -- Nanaya
finalBosses("kroldok-stronghold", false, { 3451 }) -- Overseer Mugg
finalBosses("hall-of-thanes", false, { 3496 }) -- Durgen Dirgehammer

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
ns.Data.TRACE_SECONDS = 120 -- durée de /mf trace
ns.Data.RELOAD_REMINDER_SECONDS = 3 * 3600
ns.Data.GATHERING_WINDOW = 3
ns.Data.KILLER_MEMORY = 60 -- s : une cible hostile ciblée dans ce délai avant le combat (ou pendant) est le tueur présumé
ns.Data.DEATH_RECAP_DELAY = 1 -- s après la mort avant de lire le récapitulatif du client et d'annoncer
ns.Data.TOAST_SECONDS = 10 -- durée d'affichage des textes flottants (avis de décès, appel à l'aide)
ns.Data.MAX_MOBS = 500 -- créatures distinctes gardées par personnage (clé = nom affiché)
