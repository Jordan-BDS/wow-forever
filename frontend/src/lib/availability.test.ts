import { cellsToSlots, namesByCell, slotsToCells } from "./availability";

describe("availability", () => {
  it("round-trips slots through cells and merges contiguous hours", () => {
    const slots = [
      { weekday: 1, start_hour: 20, end_hour: 23 },
      { weekday: 1, start_hour: 23, end_hour: 24 },
      { weekday: 6, start_hour: 14, end_hour: 16 },
    ];
    expect(cellsToSlots(slotsToCells(slots))).toEqual([
      { weekday: 1, start_hour: 20, end_hour: 24 },
      { weekday: 6, start_hour: 14, end_hour: 16 },
    ]);
  });

  it("splits non-contiguous hours into separate slots", () => {
    const cells = new Set(["2-9", "2-10", "2-21"]);
    expect(cellsToSlots(cells)).toEqual([
      { weekday: 2, start_hour: 9, end_hour: 11 },
      { weekday: 2, start_hour: 21, end_hour: 22 },
    ]);
  });

  it("aggregates names per cell", () => {
    const map = namesByCell([
      { weekday: 3, start_hour: 20, end_hour: 22, display_name: "A" },
      { weekday: 3, start_hour: 21, end_hour: 23, display_name: "B" },
    ]);
    expect(map.get("3-20")).toEqual(["A"]);
    expect(map.get("3-21")).toEqual(["A", "B"]);
    expect(map.get("3-22")).toEqual(["B"]);
  });
});
