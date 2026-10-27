import type { Instance } from "@/api/client";
import { dateKey, instancesFor, monthGrid } from "./events";

describe("monthGrid", () => {
  it("starts on the Monday before the 1st and covers the whole month", () => {
    const weeks = monthGrid(2026, 10); // novembre 2026 commence un dimanche
    expect(weeks[0][0].getDay()).toBe(1);
    expect(dateKey(weeks[0][0])).toBe("2026-10-26");
    expect(dateKey(weeks[0][6])).toBe("2026-11-01");
    const last = weeks.at(-1)!.at(-1)!;
    expect(last.getDay()).toBe(0);
    expect(last >= new Date(2026, 10, 30)).toBe(true);
    expect(weeks.length).toBe(6);
  });

  it("uses 5 weeks when the month fits", () => {
    expect(monthGrid(2026, 11).length).toBe(5); // décembre 2026 commence un mardi, 31 jours
  });
});

describe("instancesFor", () => {
  const instances = [
    { slug: "mc", kind: "raid" },
    { slug: "dm", kind: "dungeon" },
    { slug: "wsg", kind: "battleground" },
  ] as Instance[];

  it("filters instances by the kind matching the event type", () => {
    expect(instancesFor(instances, "raid").map((i) => i.slug)).toEqual(["mc"]);
    expect(instancesFor(instances, "pvp").map((i) => i.slug)).toEqual(["wsg"]);
    expect(instancesFor(instances, "social")).toEqual([]);
  });
});
