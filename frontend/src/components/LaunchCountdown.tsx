import { useEffect, useState } from "react";
import { LAUNCH_AT, launchPhase, splitCountdown } from "@/lib/launch";

const UNITS = [
  ["days", "jours"],
  ["hours", "heures"],
  ["minutes", "minutes"],
  ["seconds", "secondes"],
] as const;

/** Grand compte à rebours doré jusqu'à la sortie du jeu, puis un message de bienvenue pendant trois jours. */
export function LaunchCountdown() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const phase = launchPhase(now);
  if (phase === "over") return null;

  const launchLocal = LAUNCH_AT.toLocaleString("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

  if (phase === "launched") {
    return (
      <section
        className="mb-6 rounded-lg border border-gold bg-surface p-6 text-center"
        style={{
          backgroundImage: "radial-gradient(circle at 50% 0%, rgba(217,184,74,.28), transparent 65%)",
        }}
      >
        <div className="text-xs uppercase tracking-[.2em] text-gold">World of Warcraft: Forever</div>
        <div className="mt-1 font-display text-3xl text-gold-light">Les portes sont ouvertes.</div>
        <p className="mt-2 text-sm text-muted">
          Bon jeu à tous. Pensez à installer l'addon pour que vos exploits remontent ici.
        </p>
      </section>
    );
  }

  const parts = splitCountdown(LAUNCH_AT, now);
  return (
    <section
      className="mb-6 overflow-hidden rounded-lg border border-gold/70 bg-surface p-5 sm:p-6"
      style={{
        backgroundImage: "radial-gradient(circle at 50% -20%, rgba(217,184,74,.28), transparent 60%)",
      }}
      aria-label="Compte à rebours avant la sortie du jeu"
    >
      <div className="text-center">
        <div className="text-xs uppercase tracking-[.2em] text-gold">World of Warcraft: Forever</div>
        <div className="mt-1 font-display text-xl text-text sm:text-2xl">Ouverture des royaumes dans</div>
      </div>
      <div className="mx-auto mt-4 grid max-w-xl grid-cols-4 gap-2 sm:gap-3">
        {UNITS.map(([key, label]) => (
          <div key={key} className="rounded-md border border-gold/40 bg-bg/70 px-1 py-3 text-center sm:py-4">
            <div className="font-display text-3xl leading-none tabular-nums text-gold-light sm:text-5xl">
              {String(parts[key]).padStart(2, "0")}
            </div>
            <div className="mt-2 text-[11px] uppercase tracking-[.14em] text-muted">{label}</div>
          </div>
        ))}
      </div>
      <p className="mt-4 text-center text-sm text-muted">
        {launchLocal.charAt(0).toUpperCase() + launchLocal.slice(1)}, heure de Paris
      </p>
    </section>
  );
}
