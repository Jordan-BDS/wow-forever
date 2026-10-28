import { describe, expect, it } from "vitest";
import { formatValue, rankDelta, type RankingEntry } from "./sync";

const entry = (rank: number, previous_rank: number | null): RankingEntry => ({
  rank,
  previous_rank,
  user: { id: 1, display_name: "Jordan" },
  character: null,
  value: 1,
  since: null,
});

describe("rankDelta", () => {
  it("compare au rang de la période précédente", () => {
    expect(rankDelta(entry(1, 3))).toEqual({ text: "▲ 2", tone: "up" });
    expect(rankDelta(entry(4, 2))).toEqual({ text: "▼ 2", tone: "down" });
    expect(rankDelta(entry(2, 2))).toEqual({ text: "=", tone: "same" });
    expect(rankDelta(entry(5, null))).toEqual({ text: "nouveau", tone: "new" });
  });
});

describe("formatValue", () => {
  it("ajoute l'unité et garde une décimale aux flottants", () => {
    expect(formatValue({ unit: "" }, 210)).toBe("210");
    expect(formatValue({ unit: "%" }, 61)).toBe("61 %");
    expect(formatValue({ unit: "h" }, 14.25)).toBe("14.3 h");
  });
});
