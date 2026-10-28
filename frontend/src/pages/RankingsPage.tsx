import clsx from "clsx";
import { useState } from "react";
import { Link } from "react-router";
import { useGameData } from "@/api/hooks";
import {
  formatValue,
  rankDelta,
  useRankings,
  type RankingBy,
  type RankingCategory,
  type RankingPeriod,
  type Rankings,
} from "@/api/sync";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { ClassName } from "@/components/game";
import { TitleCards } from "@/components/TitleBadges";
import { Card, PageTitle, Spinner } from "@/components/ui";
import { findClass, formatDateTime } from "@/lib/game";

const PERIODS: { key: RankingPeriod; label: string }[] = [
  { key: "week", label: "Semaine" },
  { key: "month", label: "Mois" },
  { key: "season", label: "Saison" },
  { key: "all", label: "Total" },
];
const GROUPS: { key: RankingCategory["group"] | "all"; label: string }[] = [
  { key: "all", label: "Tout" },
  { key: "pve", label: "PvE" },
  { key: "pvp", label: "PvP" },
  { key: "gathering", label: "Récolte" },
  { key: "crafting", label: "Artisanat" },
  { key: "guild", label: "Guilde" },
];

function Pill({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "rounded-full border px-3 py-1 text-sm transition-colors",
        active
          ? "border-gold bg-surface-2 text-gold-light"
          : "border-border bg-surface-2 text-muted hover:text-text",
      )}
    >
      {children}
    </button>
  );
}

function shortDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Europe/Paris",
  });
}

export function RankingsPage() {
  const [period, setPeriod] = useState<RankingPeriod>("week");
  const [by, setBy] = useState<RankingBy>("player");
  const [group, setGroup] = useState<(typeof GROUPS)[number]["key"]>("all");
  const rankings = useRankings(period, by);
  const me = useCurrentUser();

  if (rankings.isPending) return <Spinner />;
  if (rankings.isError || !rankings.data)
    return <p className="text-sm text-danger">Impossible de charger les classements.</p>;
  const data = rankings.data;
  const visible = data.categories.filter((c) => (group === "all" ? c.group !== "optin" : c.group === group));
  const periodLabel = data.start
    ? `du ${shortDate(data.start)} au ${shortDate(data.end)}`
    : `depuis le début`;

  return (
    <>
      <PageTitle>Classements de la guilde</PageTitle>
      <p className="-mt-4 mb-4 text-sm text-muted">
        {periodLabel} · {data.players} joueur{data.players > 1 ? "s" : ""}, {data.characters} personnage
        {data.characters > 1 ? "s" : ""} synchronisés
      </p>

      <div className="mb-6 flex flex-wrap items-center gap-x-5 gap-y-3">
        <div className="flex flex-wrap gap-1.5">
          {PERIODS.map((p) => (
            <Pill key={p.key} active={period === p.key} onClick={() => setPeriod(p.key)}>
              {p.label}
            </Pill>
          ))}
        </div>
        <span className="hidden h-6 w-px bg-border sm:block" />
        <div className="flex gap-1.5">
          <Pill active={by === "player"} onClick={() => setBy("player")}>
            Par joueur
          </Pill>
          <Pill active={by === "character"} onClick={() => setBy("character")}>
            Par personnage
          </Pill>
        </div>
        <span className="hidden h-6 w-px bg-border sm:block" />
        <div className="flex flex-wrap gap-1.5">
          {GROUPS.map((g) => (
            <Pill key={g.key} active={group === g.key} onClick={() => setGroup(g.key)}>
              {g.label}
            </Pill>
          ))}
        </div>
      </div>

      {data.titles.length > 0 && <TitlesRow titles={data.titles} />}

      {data.characters === 0 ? (
        <Card className="text-sm text-muted">
          Aucun personnage synchronisé pour l'instant. Les classements se rempliront dès que l'addon enverra
          ses premières données.
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((category) => (
            <RankingCard key={category.key} category={category} by={by} meId={me.id} />
          ))}
        </div>
      )}

      <GuildProgression data={data} />

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <LevelsCard levels={data.levels} />
        <TotalsCard totals={data.week_totals} />
      </div>
    </>
  );
}

function TitlesRow({ titles }: { titles: Rankings["titles"] }) {
  return (
    <section className="mb-6">
      <div className="mb-2 flex flex-wrap items-baseline gap-3">
        <h2 className="font-display text-lg">Titres de la semaine</h2>
        <span className="text-xs text-muted">
          semaine du {shortDate(titles[0].week_start)} · attribués le lundi à 10h, figés ensuite
        </span>
      </div>
      <TitleCards titles={titles} />
    </section>
  );
}

function RankingCard({ category, by, meId }: { category: RankingCategory; by: RankingBy; meId: number }) {
  const gamedata = useGameData();
  const mine = category.all_entries.filter((e) => e.user_id === meId);
  const shownIds = new Set(category.entries.map((e) => `${e.user.id}-${e.character?.id ?? ""}`));
  const myHidden = by === "player" && !category.entries.some((e) => e.user.id === meId) ? mine : [];
  return (
    <Card className={clsx("space-y-2", category.shame && "border-danger/40")}>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className={clsx("font-display text-lg", category.shame && "text-danger")}>{category.label}</h2>
        <span className="text-xs uppercase tracking-wide text-muted">
          {GROUPS.find((g) => g.key === category.group)?.label}
        </span>
      </div>
      {category.note && <p className="text-xs text-muted">{category.note}</p>}
      {category.entries.length === 0 ? (
        <p className="text-sm text-muted">Personne pour l'instant sur cette période.</p>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {category.entries.map((e) => {
              const delta = rankDelta(e);
              const isMe = e.user.id === meId;
              const key = `${e.user.id}-${e.character?.id ?? ""}`;
              shownIds.add(key);
              return (
                <tr
                  key={key}
                  className={clsx("border-b border-border/60 last:border-0", isMe && "bg-surface-2/60")}
                >
                  <td
                    className={clsx(
                      "w-8 py-1.5 pr-2",
                      e.rank <= 3 && !category.shame
                        ? "text-gold-light"
                        : category.shame && e.rank <= 3
                          ? "text-danger"
                          : "text-muted",
                    )}
                  >
                    {e.rank}
                  </td>
                  <td className="py-1.5">
                    <Link
                      to={`/membres/${e.user.id}`}
                      className={clsx(isMe && "font-medium text-gold-light")}
                    >
                      {isMe ? "Toi" : e.user.display_name}
                    </Link>
                    {e.character && (
                      <span className="text-muted">
                        {" · "}
                        <Link to={`/personnages/${e.character.id}`}>
                          <ClassName playerClass={findClass(gamedata.data, e.character.player_class)}>
                            {e.character.name}
                          </ClassName>
                        </Link>
                      </span>
                    )}
                    {e.since && (
                      <span className="ml-1 text-[11px] text-muted">depuis le {shortDate(e.since)}</span>
                    )}
                  </td>
                  <td className="py-1.5 text-right font-mono">{formatValue(category, e.value)}</td>
                  <td
                    className={clsx(
                      "w-14 py-1.5 text-right text-xs",
                      delta.tone === "up" && "text-success",
                      delta.tone === "down" && "text-danger",
                      (delta.tone === "same" || delta.tone === "new") && "text-muted",
                    )}
                  >
                    {delta.text}
                  </td>
                </tr>
              );
            })}
            {myHidden.map((m) => (
              <tr key={`me-${m.user_id}`} className="border-t border-gold/30 bg-surface-2/60">
                <td className="w-8 py-1.5 pr-2 text-muted">{m.rank}</td>
                <td className="py-1.5 font-medium text-gold-light">Toi</td>
                <td className="py-1.5 text-right font-mono">{formatValue(category, m.value)}</td>
                <td />
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {category.total > category.entries.length && (
        <p className="text-xs text-muted">{category.total} classés au total.</p>
      )}
    </Card>
  );
}

function GuildProgression({ data }: { data: Rankings }) {
  const [slug, setSlug] = useState<string | null>(null);
  if (data.progression.length === 0) return null;
  const current = data.progression.find((p) => p.slug === slug) ?? data.progression[0];
  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-lg">Progression de guilde</h2>
        <div className="flex flex-wrap gap-1.5">
          {data.progression.map((p) => (
            <Pill key={p.slug} active={current.slug === p.slug} onClick={() => setSlug(p.slug)}>
              {p.name}
            </Pill>
          ))}
        </div>
      </div>
      <Card className="space-y-3">
        <div className="flex flex-wrap items-center gap-4">
          <div className="min-w-60 flex-1 space-y-1">
            <div className="flex justify-between text-sm">
              <span>
                {current.killed} boss sur {current.total} tués par la guilde
              </span>
              {current.first_clear && (
                <span className="text-muted">instance terminée le {shortDate(current.first_clear)}</span>
              )}
            </div>
            <div className="h-2.5 overflow-hidden rounded bg-bg">
              <div
                className="h-full bg-gold"
                style={{ width: `${Math.round((100 * current.killed) / Math.max(1, current.total))}%` }}
              />
            </div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-1.5 pr-3">Boss</th>
                <th className="py-1.5 pr-3">Premier kill de la guilde</th>
                <th className="py-1.5 pr-3 text-right">Kills</th>
                <th className="py-1.5 pr-3">Dernier kill</th>
                <th className="py-1.5 text-right">Guildiens</th>
              </tr>
            </thead>
            <tbody>
              {current.bosses.map((b) => (
                <tr key={b.id} className={clsx("border-t border-border/60", b.kills === 0 && "text-muted")}>
                  <td className="py-1.5 pr-3">{b.name}</td>
                  <td className="py-1.5 pr-3">{b.first_kill ? shortDate(b.first_kill) : "—"}</td>
                  <td className="py-1.5 pr-3 text-right font-mono">{b.kills || "—"}</td>
                  <td className="py-1.5 pr-3">{b.last_kill ? formatDateTime(b.last_kill) : "—"}</td>
                  <td className="py-1.5 text-right">{b.best_group || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted">
          Un kill compte pour la guilde quand au moins 5 joueurs du site étaient dans le groupe.
        </p>
      </Card>
    </section>
  );
}

function LevelsCard({ levels }: { levels: Rankings["levels"] }) {
  const max = Math.max(1, ...levels.map((l) => l.count));
  const total = levels.reduce((sum, l) => sum + l.count, 0);
  return (
    <Card className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-lg">Niveaux du roster</h2>
        <span className="text-xs text-muted">{total} personnages</span>
      </div>
      <div className="flex h-44 items-stretch gap-2">
        {levels.map((l) => {
          const height = `${Math.max(l.count > 0 ? 4 : 1, Math.round((100 * l.count) / max))}%`;
          const is60 = l.label === "60";
          return (
            <div key={l.label} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex w-full flex-1 flex-col justify-end">
                <div className={clsx("mb-1 text-center text-xs", is60 ? "text-gold-light" : "text-muted")}>
                  {l.count || ""}
                </div>
                <div
                  className={clsx("w-full rounded-t", is60 ? "bg-gold" : "bg-border")}
                  style={{ height }}
                  title={`${l.count} personnage${l.count > 1 ? "s" : ""}`}
                />
              </div>
              <span className="text-xs text-muted">{l.label}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

const TOTAL_LABELS: Record<string, string> = {
  boss_kills: "Boss tués",
  dungeons_done: "Donjons terminés",
  bg_played: "BG joués",
  "gathering.mining": "Minerais récoltés",
  crafted_total: "Objets fabriqués",
  deaths: "Morts",
};

function TotalsCard({ totals }: { totals: Record<string, number> }) {
  return (
    <Card className="space-y-3">
      <h2 className="font-display text-lg">Totaux de la guilde cette semaine</h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
        {Object.entries(TOTAL_LABELS).map(([key, label]) => (
          <div key={key} className="flex justify-between border-b border-border/60 py-1">
            <dt className="text-muted">{label}</dt>
            <dd className={clsx("font-mono", key === "deaths" && "text-danger")}>{totals[key] ?? 0}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-muted">
        Joueurs sans l'addon : non comptés. Arrivés en cours de période : marqués « depuis le ».
      </p>
    </Card>
  );
}
