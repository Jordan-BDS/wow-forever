export const STAT_LABEL: Record<string, string> = {
  strength: "Force",
  agility: "Agilité",
  stamina: "Endurance",
  intellect: "Intelligence",
  spirit: "Esprit",
  attack_power: "Puissance d'attaque",
  ranged_attack_power: "Puissance d'attaque à distance",
  spell_damage: "Dégâts des sorts",
  spell_healing: "Soins",
  spell_power: "Puissance des sorts",
  mana_regen: "Mana / 5 s",
  crit_rating: "Critique (score)",
  hit_rating: "Toucher (score)",
  defense_rating: "Défense (score)",
  dodge_rating: "Esquive (score)",
  parry_rating: "Parade (score)",
  block_rating: "Blocage (score)",
  block_value: "Valeur de blocage",
  fire_resistance: "Rés. Feu",
  frost_resistance: "Rés. Givre",
  nature_resistance: "Rés. Nature",
  shadow_resistance: "Rés. Ombre",
  arcane_resistance: "Rés. Arcanes",
  holy_resistance: "Rés. Sacré",
  bonus_armor: "Armure",
};

export const SLOT_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Tous les emplacements" },
  { value: "head", label: "Tête" },
  { value: "neck", label: "Cou" },
  { value: "shoulder", label: "Épaules" },
  { value: "back", label: "Dos" },
  { value: "chest", label: "Torse" },
  { value: "wrist", label: "Poignets" },
  { value: "hands", label: "Mains" },
  { value: "waist", label: "Taille" },
  { value: "legs", label: "Jambes" },
  { value: "feet", label: "Pieds" },
  { value: "finger", label: "Doigt" },
  { value: "trinket", label: "Bijou" },
  { value: "one_hand,main_hand", label: "Arme à une main" },
  { value: "two_hand", label: "Arme à deux mains" },
  { value: "off_hand,held_off_hand,shield", label: "Main gauche / bouclier" },
  { value: "ranged,thrown,relic", label: "À distance / relique" },
];

/** Formate les stats brutes d'un objet en texte court. */
export function formatStats(stats: Record<string, number> | undefined): string {
  const entries = Object.entries(stats ?? {});
  if (entries.length === 0) return "—";
  return entries
    .map(([key, value]) => `${value > 0 ? "+" : ""}${value} ${STAT_LABEL[key] ?? key}`)
    .join(", ");
}
