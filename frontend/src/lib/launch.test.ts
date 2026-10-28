import { describe, expect, it } from "vitest";
import { LAUNCH_AT, launchPhase, splitCountdown } from "./launch";

describe("compte à rebours", () => {
  it("découpe en jours, heures, minutes, secondes", () => {
    const now = new Date("2026-10-29T10:30:15Z");
    expect(splitCountdown(LAUNCH_AT, now)).toEqual({
      total: 563_385,
      days: 6,
      hours: 12,
      minutes: 29,
      seconds: 45,
    });
    expect(splitCountdown(LAUNCH_AT, new Date("2027-01-01T00:00:00Z")).total).toBe(0);
  });
  it("sait dans quelle phase on est", () => {
    expect(launchPhase(new Date("2026-11-04T22:59:59Z"))).toBe("before");
    expect(launchPhase(new Date("2026-11-05T12:00:00Z"))).toBe("launched");
    expect(launchPhase(new Date("2026-11-09T00:00:00Z"))).toBe("over");
  });
});
