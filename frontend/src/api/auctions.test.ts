import { describe, expect, it } from "vitest";
import { categoryPath, formatChange, formatMoney, niceTicks } from "./auctions";

describe("categoryPath", () => {
  const leaf = (key: string, label: string) => ({ key, label, children: [] });
  const tree = [
    leaf("weapon", "Armes"),
    {
      key: "armor",
      label: "Armures",
      children: [{ key: "armor.1", label: "Tissu", children: [leaf("armor.1.head", "Tête")] }],
    },
  ];

  it("donne le chemin jusqu'au type retenu, vide s'il n'existe pas", () => {
    expect(categoryPath(tree, "armor.1.head").map((c) => c.label)).toEqual(["Armures", "Tissu", "Tête"]);
    expect(categoryPath(tree, "weapon").map((c) => c.key)).toEqual(["weapon"]);
    expect(categoryPath(tree, "")).toEqual([]);
    expect(categoryPath(tree, "armor.9")).toEqual([]);
  });
});

describe("formatMoney", () => {
  it("découpe les cuivres en or, argent, cuivre et omet les parties nulles", () => {
    expect(formatMoney(123456)).toBe("12 po 34 pa 56 pc");
    expect(formatMoney(77900)).toBe("7 po 79 pa");
    expect(formatMoney(600)).toBe("6 pa");
    expect(formatMoney(7)).toBe("7 pc");
    expect(formatMoney(0)).toBe("0 pc");
  });
});

describe("formatChange", () => {
  it("signe la variation et garde une décimale sous 10 %", () => {
    expect(formatChange(25)).toBe("+25 %");
    expect(formatChange(-37.5)).toBe("−38 %");
    expect(formatChange(2.5)).toBe("+2.5 %");
    expect(formatChange(0)).toBe("=");
  });
});

describe("niceTicks", () => {
  it("couvre l'intervalle avec des pas ronds", () => {
    expect(niceTicks(0, 100, 4)).toEqual([0, 50, 100]);
    expect(niceTicks(1230, 1870, 4)).toEqual([1200, 1400, 1600, 1800, 2000]);
    expect(niceTicks(3, 5, 4)).toEqual([3, 4, 5]);
  });

  it("donne une marge à une série plate", () => {
    expect(niceTicks(100, 100, 4)).toEqual([90, 95, 100, 105, 110]);
    expect(niceTicks(0, 0, 2)).toEqual([0, 1]);
  });
});
