import { Link } from "react-router";
import { useGameData } from "@/api/hooks";
import type { WeeklyTitle } from "@/api/sync";
import { ClassName } from "@/components/game";
import { findClass } from "@/lib/game";

type Theme = { accent: string; glow: string; icon: React.ReactNode; unit: string };

const Pickaxe = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M14 10 4 20" />
    <path d="M9 5c2.5-1.5 6-1.5 8.5 1S20 12 18.5 14.5" />
    <path d="m11.5 7.5 5 5" />
  </svg>
);
const Swords = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M14.5 17.5 3 6V3h3l11.5 11.5" />
    <path d="M13 19l6-6" />
    <path d="M16 16l4 4" />
    <path d="M19 21l2-2" />
    <path d="M9.5 6.5 21 18v3h-3L6.5 9.5" />
  </svg>
);
const Flame = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M12 22c4.4 0 7-2.8 7-6.5 0-3-2-5-3.5-7.5-.5 2-1.5 3-3 3.5C12 9 12 5 9 2c0 4-3 5.5-4 9-.7 2.5-.3 6 2.5 8.5A7 7 0 0 0 12 22Z" />
  </svg>
);
const Skull = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M12 2a8 8 0 0 0-8 8c0 2.6 1.2 4.9 3 6.3V19a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2v-2.7A8 8 0 0 0 12 2Z" />
    <circle cx="9" cy="11" r="1.5" />
    <circle cx="15" cy="11" r="1.5" />
    <path d="M10 17h4" />
  </svg>
);

const THEMES: Record<string, Theme> = {
  gathering: { accent: "#d9b84a", glow: "rgba(217,184,74,.25)", icon: Pickaxe, unit: "ressources" },
  bg: { accent: "#e0604a", glow: "rgba(224,96,74,.25)", icon: Swords, unit: "joueurs tués" },
  boss: { accent: "#ff8a3d", glow: "rgba(255,138,61,.25)", icon: Flame, unit: "boss tués" },
  shame: { accent: "#b7b7b7", glow: "rgba(183,183,183,.2)", icon: Skull, unit: "morts" },
};
const DEFAULT_THEME: Theme = { accent: "#d9b84a", glow: "rgba(217,184,74,.25)", icon: Flame, unit: "" };

function value(t: WeeklyTitle, unit: string): string {
  const n = Number.isInteger(t.value) ? t.value : t.value.toFixed(1);
  return unit ? `${n} ${unit}` : String(n);
}

/** Ordre d'affichage commun aux cartes et aux « Futurs Roxors ». */
const TITLE_ORDER = ["gathering", "bg", "boss", "shame"];

/** Cartes des Roxors de la semaine passée : icône, accent, gagnant en grand, personnage à la couleur de classe. */
export function TitleCards({ titles }: { titles: WeeklyTitle[] }) {
  const gamedata = useGameData();
  const ordered = [...titles].sort((a, b) => TITLE_ORDER.indexOf(a.key) - TITLE_ORDER.indexOf(b.key));
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {ordered.map((t) => {
        const theme = THEMES[t.key] ?? DEFAULT_THEME;
        return (
          <div
            key={t.key}
            className="relative overflow-hidden rounded-lg border bg-surface p-4"
            style={{
              borderColor: theme.accent,
              backgroundImage: `radial-gradient(circle at 100% 0%, ${theme.glow}, transparent 60%)`,
            }}
          >
            <div className="flex items-start gap-3">
              <span
                className="flex size-11 shrink-0 items-center justify-center rounded-full border-2 bg-bg [&>svg]:size-6"
                style={{ borderColor: theme.accent, color: theme.accent }}
              >
                {theme.icon}
              </span>
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-[.14em]" style={{ color: theme.accent }}>
                  {t.label}
                </div>
                <Link
                  to={`/membres/${t.user.id}`}
                  className="block truncate font-display text-xl leading-tight text-text hover:text-gold-light"
                >
                  {t.user.display_name}
                </Link>
                <div className="mt-0.5 font-mono text-sm" style={{ color: theme.accent }}>
                  {value(t, theme.unit)}
                </div>
                {t.character && (
                  <div className="text-sm">
                    <Link to={`/personnages/${t.character.id}`}>
                      <ClassName playerClass={findClass(gamedata.data, t.character.player_class)}>
                        {t.character.name}
                      </ClassName>
                    </Link>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
