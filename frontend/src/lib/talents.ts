import type { components } from "@/api/schema";

export type TalentData = components["schemas"]["Talent"];
export type TalentTreeData = components["schemas"]["TalentTree"];

export const MAX_POINTS = 51; // 1 point par niveau à partir du niveau 10, niveau 60
export const POINTS_PER_TIER = 5;
export const COLUMNS = 4;

/** Points investis par talent, indexés par ID de talent. */
export type Build = Record<number, number>;

export function sortedTalents(tree: TalentTreeData): TalentData[] {
  return [...tree.talents].sort((a, b) => a.row - b.row || a.column - b.column);
}

export function pointsInTree(tree: TalentTreeData, build: Build): number {
  return tree.talents.reduce((sum, t) => sum + (build[t.id] ?? 0), 0);
}

export function totalPoints(trees: TalentTreeData[], build: Build): number {
  return trees.reduce((sum, tree) => sum + pointsInTree(tree, build), 0);
}

/** Points investis dans les rangées strictement au-dessus de `row`. */
function pointsAbove(tree: TalentTreeData, build: Build, row: number): number {
  return tree.talents.filter((t) => t.row < row).reduce((sum, t) => sum + (build[t.id] ?? 0), 0);
}

/** Un état est valide si chaque talent investi a sa rangée débloquée et son prérequis satisfait. */
export function isValid(tree: TalentTreeData, build: Build): boolean {
  const byId = new Map(tree.talents.map((t) => [t.id, t]));
  for (const talent of tree.talents) {
    const points = build[talent.id] ?? 0;
    if (points === 0) continue;
    if (points > talent.max_rank) return false;
    if (pointsAbove(tree, build, talent.row) < POINTS_PER_TIER * talent.row) return false;
    if (talent.prerequisite != null) {
      const prereq = byId.get(talent.prerequisite);
      const required = talent.prerequisite_rank || prereq?.max_rank || 1;
      if ((build[talent.prerequisite] ?? 0) < required) return false;
    }
  }
  return true;
}

export function canAdd(
  trees: TalentTreeData[],
  tree: TalentTreeData,
  talent: TalentData,
  build: Build,
): boolean {
  if (totalPoints(trees, build) >= MAX_POINTS) return false;
  if ((build[talent.id] ?? 0) >= talent.max_rank) return false;
  return isValid(tree, { ...build, [talent.id]: (build[talent.id] ?? 0) + 1 });
}

export function canRemove(tree: TalentTreeData, talent: TalentData, build: Build): boolean {
  if ((build[talent.id] ?? 0) === 0) return false;
  return isValid(tree, { ...build, [talent.id]: build[talent.id] - 1 });
}

/** Rangée accessible (pour l'affichage) : assez de points au-dessus. */
export function tierUnlocked(tree: TalentTreeData, build: Build, row: number): boolean {
  return pointsAbove(tree, build, row) >= POINTS_PER_TIER * row;
}

/** Encodage partageable : un chiffre par talent (ordre rangée/colonne), arbres séparés par « - », zéros finaux retirés. */
export function encodeBuild(trees: TalentTreeData[], build: Build): string {
  return trees
    .map((tree) =>
      sortedTalents(tree)
        .map((t) => String(build[t.id] ?? 0))
        .join("")
        .replace(/0+$/, ""),
    )
    .join("-");
}

export function decodeBuild(trees: TalentTreeData[], encoded: string): Build {
  const build: Build = {};
  const parts = encoded.split("-");
  trees.forEach((tree, index) => {
    const digits = parts[index] ?? "";
    sortedTalents(tree).forEach((talent, position) => {
      const value = Number(digits[position] ?? 0);
      if (value > 0) build[talent.id] = Math.min(value, talent.max_rank);
    });
  });
  // On ne garde que ce qui est cohérent, arbre par arbre.
  for (const tree of trees) {
    if (!isValid(tree, build)) {
      for (const t of tree.talents) delete build[t.id];
    }
  }
  return build;
}

/** Arbre le plus investi, pour nommer la spécialisation. */
export function dominantTree(trees: TalentTreeData[], build: Build): TalentTreeData | undefined {
  const [best] = [...trees].sort((a, b) => pointsInTree(b, build) - pointsInTree(a, build));
  return best && pointsInTree(best, build) > 0 ? best : undefined;
}
