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
import { Card, PageTitle, Pill, Spinner } from "@/components/ui";
import { findClass, formatDateTime, weekSpan } from "@/lib/game";

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

      {data.titles.length > 0 && (
        <TitlesRow titles={data.titles} mob={data.mob_of_week.previous} wanted={data.most_wanted} />
      )}

      <h2 className="font-display text-lg">Classements</h2>
      <p className="mb-4 text-sm text-muted">
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

      <WantedBoard wanted={data.wanted} periodLabel={periodLabel} />

      <HuntingBoard mobs={data.mobs} meId={me.id} periodLabel={periodLabel} />

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <LevelsCard levels={data.levels} />
        <TotalsCard totals={data.week_totals} />
      </div>
    </>
  );
}

function TitlesRow({
  titles,
  mob,
  wanted,
}: {
  titles: Rankings["titles"];
  mob: Rankings["mob_of_week"]["previous"];
  wanted: Rankings["most_wanted"];
}) {
  return (
    <section className="mb-8">
      <div className="mb-2 flex flex-wrap items-baseline gap-3">
        <h2 className="font-display text-lg">Roxors de la semaine passée</h2>
        <span className="text-xs text-muted">
          {weekSpan(titles[0].week_start)} · attribués lundi à minuit, figés ensuite
        </span>
      </div>
      <TitleCards titles={titles} mob={mob} wanted={wanted} />
    </section>
  );
}

function WantedBoard({ wanted, periodLabel }: { wanted: Rankings["wanted"]; periodLabel: string }) {
  const gamedata = useGameData();
  if (wanted.length === 0) return null;
  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-display text-lg text-danger">
          <Link to="/wanted" className="hover:text-danger">
            Wanted — têtes mises à prix
          </Link>
        </h2>
        <span className="text-xs text-muted">
          {periodLabel} · un point par membre tué, jamais remis à zéro ·{" "}
          <Link to="/wanted">tout le détail</Link>
        </span>
      </div>
      <Card className="space-y-3 border-danger/40">
        <div className="nav-scroll -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <table className="w-full min-w-[40rem] whitespace-nowrap text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="w-8 py-1.5 pr-2">#</th>
                <th className="py-1.5 pr-3">Ennemi</th>
                <th className="py-1.5 pr-3 text-right">Prime</th>
                <th className="py-1.5 pr-3 text-right">Abattu</th>
                <th className="py-1.5 pr-3">Dernière victime</th>
                <th className="py-1.5">Dernier chasseur</th>
              </tr>
            </thead>
            <tbody>
              {wanted.map((e, i) => (
                <tr key={e.key} className="border-t border-border/60">
                  <td className={clsx("py-1.5 pr-2", i < 3 ? "text-danger" : "text-muted")}>{i + 1}</td>
                  <td className="py-1.5 pr-3">
                    <ClassName playerClass={findClass(gamedata.data, e.class)}>{e.name}</ClassName>
                    {e.victims > 1 && <span className="ml-1 text-xs text-muted">{e.victims} victimes</span>}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono text-danger">{e.points}</td>
                  <td className="py-1.5 pr-3 text-right font-mono">{e.kills || "—"}</td>
                  <td className="py-1.5 pr-3">
                    {e.last_death ? (
                      <>
                        <Link to={`/personnages/${e.last_death.victim.character.id}`}>
                          <ClassName
                            playerClass={findClass(gamedata.data, e.last_death.victim.character.player_class)}
                          >
                            {e.last_death.victim.character.name}
                          </ClassName>
                        </Link>
                        <span className="text-muted">
                          {" · "}
                          {e.last_death.zone || "?"}
                          {" · "}
                          {formatDateTime(e.last_death.at)}
                        </span>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="py-1.5">
                    {e.last_kill ? (
                      <>
                        <Link to={`/membres/${e.last_kill.by.user.id}`}>
                          {e.last_kill.by.user.display_name}
                        </Link>
                        <span className="text-muted">
                          {" · "}
                          {formatDateTime(e.last_kill.at)}
                        </span>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted">
          Lu par l'addon : le tueur d'un membre (joueur ciblé) et les joueurs abattus (message de victoire
          honorable). Un kill compte une fois par minute pour tout le groupe ; un PNJ homonyme se retire
          depuis l'administration.
        </p>
      </Card>
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
                  <td className="whitespace-nowrap py-1.5 pl-2 text-right font-mono">
                    {formatValue(category, e.value)}
                  </td>
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
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap justify-between gap-x-3 text-sm">
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
        <div className="nav-scroll -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <table className="w-full min-w-[36rem] whitespace-nowrap text-sm">
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

function HuntingBoard({
  mobs,
  meId,
  periodLabel,
}: {
  mobs: Rankings["mobs"];
  meId: number;
  periodLabel: string;
}) {
  const gamedata = useGameData();
  const [expanded, setExpanded] = useState(false);
  if (mobs.length === 0) return null;
  const shown = expanded ? mobs : mobs.slice(0, 15);
  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-display text-lg">Tableau de chasse de la guilde</h2>
        <span className="text-xs text-muted">
          {periodLabel} · toute créature frappée dans les 15 s avant sa mort
        </span>
      </div>
      <Card className="space-y-3">
        <div className="nav-scroll -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <table className="w-full min-w-[36rem] whitespace-nowrap text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="w-8 py-1.5 pr-2">#</th>
                <th className="py-1.5 pr-3">Créature</th>
                <th className="py-1.5 pr-3 text-right">Kills</th>
                <th className="py-1.5 pr-3 text-right">Chasseurs</th>
                <th className="py-1.5 pr-3">Meilleur chasseur</th>
                <th className="py-1.5">Dernier kill</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((m, i) => {
                const isMe = m.top?.user.id === meId;
                return (
                  <tr key={m.key} className="border-t border-border/60">
                    <td className={clsx("py-1.5 pr-2", i < 3 ? "text-gold-light" : "text-muted")}>{i + 1}</td>
                    <td className="py-1.5 pr-3">{m.name}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{m.kills}</td>
                    <td className="py-1.5 pr-3 text-right text-muted">{m.hunters}</td>
                    <td className="py-1.5 pr-3">
                      {m.top ? (
                        <>
                          <Link
                            to={`/membres/${m.top.user.id}`}
                            className={clsx(isMe && "font-medium text-gold-light")}
                          >
                            {isMe ? "Toi" : m.top.user.display_name}
                          </Link>
                          <span className="text-muted">
                            {" · "}
                            <Link to={`/personnages/${m.top.character.id}`}>
                              <ClassName playerClass={findClass(gamedata.data, m.top.character.player_class)}>
                                {m.top.character.name}
                              </ClassName>
                            </Link>
                            {" · "}
                            <span className="font-mono">{m.top.kills}</span>
                          </span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-1.5 text-muted">{m.last_kill ? formatDateTime(m.last_kill) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {mobs.length > 15 && (
          <button
            type="button"
            className="text-sm text-muted hover:text-text"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "Voir moins" : `Voir les ${mobs.length} créatures`}
          </button>
        )}
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
  kills: "Créatures tuées",
  bg_played: "BG joués",
  gathering_total: "Ressources récoltées",
  crafted_total: "Objets fabriqués",
  deaths: "Morts",
};

function TotalsCard({ totals }: { totals: Record<string, number> }) {
  return (
    <Card className="space-y-3">
      <h2 className="font-display text-lg">Totaux de la guilde cette semaine</h2>
      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
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
