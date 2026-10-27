import type { Character, GameRole } from "@/api/client";

export type CompositionMode = "mains" | "sixty" | "all";

export const COMPOSITION_MODES: { value: CompositionMode; label: string }[] = [
  { value: "mains", label: "Mains" },
  { value: "sixty", label: "Niveau 60" },
  { value: "all", label: "Tous" },
];

export interface Composition {
  total: number;
  roles: Record<GameRole, number>;
  classes: Record<string, number>;
}

export function selectForComposition(characters: Character[], mode: CompositionMode): Character[] {
  if (mode === "mains") return characters.filter((c) => c.is_main);
  if (mode === "sixty") return characters.filter((c) => c.level === 60);
  return characters;
}

export function summarize(characters: Character[], mode: CompositionMode): Composition {
  const selected = selectForComposition(characters, mode);
  const roles: Record<GameRole, number> = { tank: 0, heal: 0, dps: 0 };
  const classes: Record<string, number> = {};
  for (const c of selected) {
    roles[c.main_role] += 1;
    classes[c.player_class] = (classes[c.player_class] ?? 0) + 1;
  }
  return { total: selected.length, roles, classes };
}

/** Regroupe les persos par joueur : le main d'abord, puis les alts par niveau. */
export function groupByOwner(characters: Character[]): { main: Character; alts: Character[] }[] {
  const byOwner = new Map<number, Character[]>();
  for (const c of characters) byOwner.set(c.owner.id, [...(byOwner.get(c.owner.id) ?? []), c]);
  return [...byOwner.values()]
    .map((list) => {
      const sorted = [...list].sort(
        (a, b) => Number(b.is_main) - Number(a.is_main) || (b.level ?? 0) - (a.level ?? 0),
      );
      return { main: sorted[0], alts: sorted.slice(1) };
    })
    .sort((a, b) => a.main.name.localeCompare(b.main.name, "fr"));
}
