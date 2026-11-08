import { Link } from "react-router";
import { useGameData } from "@/api/hooks";
import type { GuildMob, WeeklyTitle } from "@/api/sync";
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

const Claw = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M5 3c2 4 2 9 1 18" />
    <path d="M10 3c2 4 2.5 9 1.5 18" />
    <path d="M15 4c2 4 2 9 1 17" />
    <path d="M20 6c1 4 .5 8-1 15" />
  </svg>
);

const Paw = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <circle cx="6" cy="9" r="2" />
    <circle cx="18" cy="9" r="2" />
    <circle cx="9.5" cy="4.5" r="2" />
    <circle cx="14.5" cy="4.5" r="2" />
    <path d="M12 10c-3 0-6 3-6 6a3 3 0 0 0 4 3c.7-.3 1.3-.5 2-.5s1.3.2 2 .5a3 3 0 0 0 4-3c0-3-3-6-6-6Z" />
  </svg>
);

const Hammer = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="m15 12-8.373 8.373a1 1 0 1 1-3-3L12 9" />
    <path d="m18 15 4-4" />
    <path d="m21.5 11.5-1.914-1.914A2 2 0 0 1 19 8.172V7l-2.26-2.26a6 6 0 0 0-4.202-1.756L9 2.96l.92.82A6.18 6.18 0 0 1 12 8.4V10l2 2h1.172a2 2 0 0 1 1.414.586L18.5 14.5" />
  </svg>
);

const Scroll = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M19 17V5a2 2 0 0 0-2-2H4" />
    <path d="M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3" />
  </svg>
);

const Fish = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M6.5 12c.94-3.46 4.94-6 8.5-6 3.56 0 6.06 2.54 7 6-.94 3.47-3.44 6-7 6s-7.56-2.53-8.5-6Z" />
    <path d="M18 12v.5" />
    <path d="M16 17.93a9.77 9.77 0 0 1 0-11.86" />
    <path d="M7 10.67C7 8 5.58 5.97 2.73 5.5c-1 1.5-1 5 .23 6.5-1.24 1.5-1.24 5-.23 6.5C5.58 18.03 7 16 7 13.33" />
    <path d="M10.46 7.26C10.2 5.88 9.17 4.24 8 3h5.8a2 2 0 0 1 1.98 1.67l.23 1.4" />
    <path d="m16.01 17.93-.23 1.4A2 2 0 0 1 13.8 21H9.5a5.96 5.96 0 0 0 1.49-3.98" />
  </svg>
);

const THEMES: Record<string, Theme> = {
  gathering: { accent: "#d9b84a", glow: "rgba(217,184,74,.25)", icon: Pickaxe, unit: "ressources" },
  bg: { accent: "#e0604a", glow: "rgba(224,96,74,.25)", icon: Swords, unit: "joueurs tués" },
  boss: { accent: "#ff8a3d", glow: "rgba(255,138,61,.25)", icon: Flame, unit: "boss tués" },
  kills: { accent: "#8fd14f", glow: "rgba(143,209,79,.25)", icon: Claw, unit: "créatures tuées" },
  shame: { accent: "#b7b7b7", glow: "rgba(183,183,183,.2)", icon: Skull, unit: "morts" },
  crafting: { accent: "#c08457", glow: "rgba(192,132,87,.25)", icon: Hammer, unit: "objets" },
  quests: { accent: "#4fc7b5", glow: "rgba(79,199,181,.25)", icon: Scroll, unit: "quêtes" },
  fishing: { accent: "#5aa9e6", glow: "rgba(90,169,230,.25)", icon: Fish, unit: "poissons" },
};
const DEFAULT_THEME: Theme = { accent: "#d9b84a", glow: "rgba(217,184,74,.25)", icon: Flame, unit: "" };

function value(t: WeeklyTitle, unit: string): string {
  const n = Number.isInteger(t.value) ? t.value : t.value.toFixed(1);
  return unit ? `${n} ${unit}` : String(n);
}

/** Ordre d'affichage commun aux cartes et aux « Futurs Roxors ». */
const TITLE_ORDER = ["gathering", "bg", "boss", "kills", "shame", "crafting", "quests", "fishing"];

const MOB_THEME: Theme = { accent: "#c47bff", glow: "rgba(196,123,255,.25)", icon: Paw, unit: "fois tué" };

/** Cartes des Roxors de la semaine passée : icône, accent, gagnant en grand, personnage à la couleur de classe.
 *  Avec `mob`, une sixième carte : la créature la plus tuée par la guilde cette semaine-là. */
export function TitleCards({ titles, mob }: { titles: WeeklyTitle[]; mob?: GuildMob | null }) {
  const gamedata = useGameData();
  const ordered = [...titles].sort((a, b) => TITLE_ORDER.indexOf(a.key) - TITLE_ORDER.indexOf(b.key));
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
      {mob && (
        <div
          className="relative overflow-hidden rounded-lg border bg-surface p-4"
          style={{
            borderColor: MOB_THEME.accent,
            backgroundImage: `radial-gradient(circle at 100% 0%, ${MOB_THEME.glow}, transparent 60%)`,
          }}
        >
          <div className="flex items-start gap-3">
            <span
              className="flex size-11 shrink-0 items-center justify-center rounded-full border-2 bg-bg [&>svg]:size-6"
              style={{ borderColor: MOB_THEME.accent, color: MOB_THEME.accent }}
            >
              {MOB_THEME.icon}
            </span>
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-[.14em]" style={{ color: MOB_THEME.accent }}>
                Souffre-douleur
              </div>
              <div className="truncate font-display text-xl leading-tight text-text">{mob.name}</div>
              <div className="mt-0.5 font-mono text-sm" style={{ color: MOB_THEME.accent }}>
                {mob.kills} {MOB_THEME.unit}
              </div>
              {mob.top && (
                <div className="text-sm">
                  <span className="text-muted">surtout par </span>
                  <Link to={`/personnages/${mob.top.character.id}`}>
                    <ClassName playerClass={findClass(gamedata.data, mob.top.character.player_class)}>
                      {mob.top.character.name}
                    </ClassName>
                  </Link>
                  <span className="text-muted"> ({mob.top.kills})</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
