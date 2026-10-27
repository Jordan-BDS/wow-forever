import type { Character } from "@/api/client";
import { groupByOwner, summarize } from "./roster";

function character(overrides: Partial<Character> & { name: string }): Character {
  return {
    id: Math.floor(Math.random() * 1e6),
    owner: { id: 1, display_name: "Jo", avatar_url: "" },
    player_class: "warrior",
    race: "orc",
    level: 60,
    main_role: "dps",
    off_role: "",
    specialization: null,
    is_main: false,
    note: "",
    professions: [],
    source: "manual",
    external_id: "",
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

const roster = [
  character({ name: "Tankou", player_class: "warrior", main_role: "tank", is_main: true }),
  character({ name: "Soigne", player_class: "priest", main_role: "heal", is_main: true, level: 42, owner: { id: 2, display_name: "B", avatar_url: "" } }),
  character({ name: "Altmage", player_class: "mage", main_role: "dps", level: 60, owner: { id: 2, display_name: "B", avatar_url: "" } }),
]; // prettier-ignore

describe("summarize", () => {
  it("counts mains by role and class", () => {
    const s = summarize(roster, "mains");
    expect(s.total).toBe(2);
    expect(s.roles).toEqual({ tank: 1, heal: 1, dps: 0 });
    expect(s.classes).toEqual({ warrior: 1, priest: 1 });
  });

  it("filters level 60 regardless of main status", () => {
    expect(summarize(roster, "sixty").classes).toEqual({ warrior: 1, mage: 1 });
    expect(summarize(roster, "all").total).toBe(3);
  });
});

describe("groupByOwner", () => {
  it("puts the main first and alts after, sorted by main name", () => {
    const groups = groupByOwner(roster);
    expect(groups.map((g) => g.main.name)).toEqual(["Soigne", "Tankou"]);
    expect(groups[0].alts.map((a) => a.name)).toEqual(["Altmage"]);
  });
});
