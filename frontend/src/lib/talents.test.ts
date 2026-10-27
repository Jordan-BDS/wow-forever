import { canAdd, canRemove, decodeBuild, encodeBuild, isValid, type TalentTreeData } from "./talents";

function talent(id: number, row: number, column: number, max_rank: number, prerequisite: number | null = null) {
  return { id, name: `T${id}`, icon: "", icon_url: "", row, column, rank_spells: [], max_rank, prerequisite, prerequisite_rank: 0 };
} // prettier-ignore

const fire: TalentTreeData = {
  id: 41,
  name: "Feu",
  background: "",
  order: 1,
  talents: [talent(1, 0, 0, 5), talent(2, 0, 1, 3), talent(3, 1, 1, 5), talent(4, 2, 1, 1, 3)],
};
const frost: TalentTreeData = {
  id: 61,
  name: "Givre",
  background: "",
  order: 2,
  talents: [talent(10, 0, 0, 5)],
};
const trees = [fire, frost];

describe("talent rules", () => {
  it("unlocks a tier only with 5 points per row above it", () => {
    expect(canAdd(trees, fire, fire.talents[2], { 1: 4 })).toBe(false);
    expect(canAdd(trees, fire, fire.talents[2], { 1: 5 })).toBe(true);
    expect(canAdd(trees, fire, fire.talents[2], { 1: 3, 2: 2 })).toBe(true);
  });

  it("requires the prerequisite at full rank", () => {
    const base = { 1: 5, 2: 3, 3: 2 };
    expect(canAdd(trees, fire, fire.talents[3], base)).toBe(false);
    expect(canAdd(trees, fire, fire.talents[3], { ...base, 3: 5 })).toBe(true);
  });

  it("refuses to remove a point that would break a higher tier", () => {
    const build = { 1: 5, 3: 1 };
    expect(canRemove(fire, fire.talents[0], build)).toBe(false);
    expect(canRemove(fire, fire.talents[2], build)).toBe(true);
  });

  it("caps at 51 points overall and at the talent max rank", () => {
    const build: Record<number, number> = { 1: 5 };
    expect(canAdd(trees, fire, fire.talents[0], build)).toBe(false);
    expect(isValid(fire, { 1: 6 })).toBe(false);
  });

  it("round-trips through the share encoding and drops inconsistent input", () => {
    const build = { 1: 5, 2: 1, 3: 2, 10: 3 };
    const encoded = encodeBuild(trees, build);
    expect(encoded).toBe("512-3");
    expect(decodeBuild(trees, encoded)).toEqual(build);
    expect(decodeBuild(trees, "0051-3")).toEqual({ 10: 3 }); // rangée 1 sans les 5 points : arbre ignoré
  });
});
