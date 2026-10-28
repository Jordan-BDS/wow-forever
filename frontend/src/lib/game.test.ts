import { describe, expect, it } from "vitest";
import { formatAgo } from "./game";

describe("formatAgo", () => {
  const now = new Date("2026-12-21T20:00:00Z");
  it("gradue minutes, heures et jours", () => {
    expect(formatAgo("2026-12-21T19:59:40Z", now)).toBe("à l'instant");
    expect(formatAgo("2026-12-21T19:30:00Z", now)).toBe("il y a 30 min");
    expect(formatAgo("2026-12-21T17:00:00Z", now)).toBe("il y a 3 h");
    expect(formatAgo("2026-12-20T10:00:00Z", now)).toBe("il y a 34 h");
    expect(formatAgo("2026-12-10T10:00:00Z", now)).toBe("il y a 11 j");
  });
});
