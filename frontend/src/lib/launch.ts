/** Sortie de World of Warcraft: Forever : 4 novembre 2026, 15h heure du Pacifique, soit minuit à Paris. */
export const LAUNCH_AT = new Date("2026-11-04T23:00:00Z");

export type Countdown = { days: number; hours: number; minutes: number; seconds: number; total: number };

export function splitCountdown(target: Date, now: Date): Countdown {
  const total = Math.max(0, Math.floor((target.getTime() - now.getTime()) / 1000));
  return {
    total,
    days: Math.floor(total / 86_400),
    hours: Math.floor((total % 86_400) / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60,
  };
}

/** Le compte à rebours s'affiche jusqu'au lancement, puis le message de sortie pendant trois jours. */
export function launchPhase(now: Date, target = LAUNCH_AT): "before" | "launched" | "over" {
  const diff = now.getTime() - target.getTime();
  if (diff < 0) return "before";
  if (diff < 3 * 86_400_000) return "launched";
  return "over";
}
