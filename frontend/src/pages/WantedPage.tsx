import clsx from "clsx";
import { useState } from "react";
import { Link } from "react-router";
import { useGameData } from "@/api/hooks";
import { useWantedReport, type RankingPeriod, type WantedEnemyDetail, type WantedReport } from "@/api/sync";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { CharacterName, ClassName } from "@/components/game";
import { Card, PageTitle, Pill, Spinner } from "@/components/ui";
import { findClass, formatDateTime } from "@/lib/game";

const PERIODS: { key: RankingPeriod; label: string }[] = [
  { key: "week", label: "Semaine" },
  { key: "month", label: "Mois" },
  { key: "season", label: "Saison" },
  { key: "all", label: "Total" },
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

/** Wanted : les têtes mises à prix de la guilde, avec le détail de chaque ennemi, les chasseurs et les victimes. */
export function WantedPage() {
  const [period, setPeriod] = useState<RankingPeriod>("season");
  const report = useWantedReport(period);
  const me = useCurrentUser();

  if (report.isPending) return <Spinner />;
  if (report.isError || !report.data)
    return <p className="text-sm text-danger">Impossible de charger le tableau Wanted.</p>;
  const data = report.data;
  const periodLabel = data.start
    ? `du ${shortDate(data.start)} au ${shortDate(data.end)}`
    : "depuis le début";

  return (
    <>
      <PageTitle>Wanted — têtes mises à prix</PageTitle>
      <p className="mb-4 text-sm text-muted">
        Un joueur adverse qui tue un membre prend un point de prime, jamais remis à zéro. L'abattre rapporte
        sa prime du moment au chasseur et à tout son groupe. {periodLabel}.
      </p>

      <div className="mb-6 flex flex-wrap gap-1.5">
        {PERIODS.map((p) => (
          <Pill key={p.key} active={period === p.key} onClick={() => setPeriod(p.key)}>
            {p.label}
          </Pill>
        ))}
      </div>

      <Totals totals={data.totals} />

      {data.enemies.length === 0 ? (
        <Card className="mt-6 text-sm text-muted">
          Aucune tête mise à prix sur cette période : aucun membre équipé de l'addon n'a été tué par un
          joueur.
        </Card>
      ) : (
        <section className="mt-6 space-y-3">
          {data.enemies.map((enemy, i) => (
            <EnemyCard key={enemy.key} enemy={enemy} rank={i + 1} meId={me.id} />
          ))}
        </section>
      )}

      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <HuntersCard hunters={data.hunters} meId={me.id} />
        <VictimsCard victims={data.victims} meId={me.id} />
      </div>

      <p className="mt-6 text-xs text-muted">
        Lu par l'addon : le tueur d'un membre (joueur ciblé, récapitulatif de mort) et les joueurs abattus
        (message de victoire honorable). Un kill compte une fois par minute pour tout le groupe ; chaque
        chasseur du groupe encaisse la prime. Un PNJ homonyme se retire depuis l'administration. Les{" "}
        <Link to="/classements">classements</Link> « Joueurs abattus » et « Primes encaissées » suivent les
        mêmes compteurs.
      </p>
    </>
  );
}

function Totals({ totals }: { totals: WantedReport["totals"] }) {
  const items: { label: string; value: number; tone?: string }[] = [
    { label: "Têtes mises à prix", value: totals.enemies, tone: "text-danger" },
    { label: "Points de prime", value: totals.points, tone: "text-danger" },
    { label: "Recherchés abattus", value: totals.kills, tone: "text-gold-light" },
    { label: "Chasseurs", value: totals.hunters },
    { label: "Membres tués", value: totals.victims },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {items.map((item) => (
        <Card key={item.label} className="py-3">
          <div className={clsx("font-mono text-2xl", item.tone ?? "text-text")}>{item.value}</div>
          <div className="text-xs uppercase tracking-wide text-muted">{item.label}</div>
        </Card>
      ))}
    </div>
  );
}

function EnemyCard({ enemy, rank, meId }: { enemy: WantedEnemyDetail; rank: number; meId: number }) {
  const gamedata = useGameData();
  const [open, setOpen] = useState(rank <= 3);
  const playerClass = findClass(gamedata.data, enemy.class);
  return (
    <Card className={clsx("space-y-3", rank <= 3 && "border-danger/40")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span
            className={clsx(
              "flex size-10 shrink-0 items-center justify-center rounded-full border-2 font-mono text-sm",
              rank <= 3 ? "border-danger text-danger" : "border-border text-muted",
            )}
          >
            {rank}
          </span>
          <div className="min-w-0">
            <div className="font-display text-xl leading-tight">
              <ClassName playerClass={playerClass}>{enemy.name}</ClassName>
            </div>
            <div className="text-sm text-muted">
              {playerClass?.name ?? "Classe inconnue"}
              {enemy.first_seen && <> · recherché depuis le {shortDate(enemy.first_seen)}</>}
              {enemy.zones.length > 0 && <> · sévit à {enemy.zones.map((z) => z.zone).join(", ")}</>}
            </div>
          </div>
        </div>
        <div className="flex gap-6 text-right">
          <div>
            <div className="font-mono text-2xl text-danger">{enemy.points}</div>
            <div className="text-xs uppercase tracking-wide text-muted">prime</div>
          </div>
          <div>
            <div className="font-mono text-2xl text-gold-light">{enemy.kills}</div>
            <div className="text-xs uppercase tracking-wide text-muted">abattu</div>
          </div>
          <div>
            <div className="font-mono text-2xl">{enemy.victims}</div>
            <div className="text-xs uppercase tracking-wide text-muted">
              victime{enemy.victims > 1 ? "s" : ""}
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted">
        {enemy.last_death && (
          <span>
            Dernière victime : <Who who={enemy.last_death.victim} meId={meId} gamedata={gamedata.data} /> ·{" "}
            {enemy.last_death.zone || "?"} · {formatDateTime(enemy.last_death.at)}
          </span>
        )}
        {enemy.last_kill && (
          <span>
            Dernier chasseur : <Who who={enemy.last_kill.by} meId={meId} gamedata={gamedata.data} /> ·{" "}
            {formatDateTime(enemy.last_kill.at)}
          </span>
        )}
        {!enemy.last_kill && <span className="text-danger">Jamais abattu</span>}
      </div>
      <button type="button" className="text-sm text-muted hover:text-text" onClick={() => setOpen(!open)}>
        {open
          ? "Masquer le détail"
          : `Voir le détail (${enemy.deaths.length} morts, ${enemy.kill_list.length} kills)`}
      </button>
      {open && (
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="mb-1 text-xs uppercase tracking-wide text-danger">Membres tués</h3>
            <ul className="space-y-1 text-sm">
              {enemy.deaths.map((d, i) => (
                <li
                  key={`${d.at}-${i}`}
                  className="flex flex-wrap justify-between gap-x-3 border-b border-border/60 py-1"
                >
                  <span>
                    <Who who={d.victim} meId={meId} gamedata={gamedata.data} />
                    <span className="text-muted"> · {d.zone || "?"}</span>
                  </span>
                  <span className="text-muted">{formatDateTime(d.at)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="mb-1 text-xs uppercase tracking-wide text-gold-light">Abattu par la guilde</h3>
            {enemy.kill_list.length === 0 ? (
              <p className="text-sm text-muted">Personne ne l'a encore eu.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {enemy.kill_list.map((k, i) => (
                  <li
                    key={`${k.at}-${i}`}
                    className="flex flex-wrap justify-between gap-x-3 border-b border-border/60 py-1"
                  >
                    <span>
                      <Who who={k.by} meId={meId} gamedata={gamedata.data} />
                      {k.hunters.length > 1 && (
                        <span className="text-muted"> avec {k.hunters.slice(1).join(", ")}</span>
                      )}
                      <span className="text-muted"> · {k.zone || "?"}</span>
                      {k.prime > 0 && <span className="text-gold-light"> · prime {k.prime}</span>}
                    </span>
                    <span className="text-muted">{formatDateTime(k.at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

function Who({
  who,
  meId,
  gamedata,
}: {
  who: WantedEnemyDetail["last_death"] extends infer T ? (T extends { victim: infer W } ? W : never) : never;
  meId: number;
  gamedata: ReturnType<typeof useGameData>["data"];
}) {
  const isMe = who.user.id === meId;
  return (
    <>
      <Link to={`/personnages/${who.character.id}`}>
        <CharacterName
          name={who.character.name}
          surname={who.character.surname}
          playerClass={findClass(gamedata, who.character.player_class)}
        />
      </Link>
      <span className="text-muted">
        {" "}
        (
        <Link to={`/membres/${who.user.id}`} className={clsx(isMe && "font-medium text-gold-light")}>
          {isMe ? "toi" : who.user.display_name}
        </Link>
        )
      </span>
    </>
  );
}

function HuntersCard({ hunters, meId }: { hunters: WantedReport["hunters"]; meId: number }) {
  const gamedata = useGameData();
  return (
    <Card className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-lg text-gold-light">Chasseurs de primes</h2>
        <span className="text-xs text-muted">primes encaissées · kills</span>
      </div>
      {hunters.length === 0 ? (
        <p className="text-sm text-muted">Aucun recherché abattu sur cette période.</p>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {hunters.map((h, i) => {
              const isMe = h.user.id === meId;
              return (
                <tr
                  key={h.user.id}
                  className={clsx("border-b border-border/60 last:border-0", isMe && "bg-surface-2/60")}
                >
                  <td className={clsx("w-8 py-1.5 pr-2", i < 3 ? "text-gold-light" : "text-muted")}>
                    {i + 1}
                  </td>
                  <td className="py-1.5">
                    <Link
                      to={`/membres/${h.user.id}`}
                      className={clsx(isMe && "font-medium text-gold-light")}
                    >
                      {isMe ? "Toi" : h.user.display_name}
                    </Link>
                    <span className="text-muted">
                      {" · "}
                      <Link to={`/personnages/${h.character.id}`}>
                        <CharacterName
                          name={h.character.name}
                          surname={h.character.surname}
                          playerClass={findClass(gamedata.data, h.character.player_class)}
                        />
                      </Link>
                    </span>
                  </td>
                  <td className="whitespace-nowrap py-1.5 pl-2 text-right font-mono text-gold-light">
                    {h.bounty}
                  </td>
                  <td className="whitespace-nowrap py-1.5 pl-2 text-right font-mono text-muted">
                    {h.kills} kill{h.kills > 1 ? "s" : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function VictimsCard({ victims, meId }: { victims: WantedReport["victims"]; meId: number }) {
  const gamedata = useGameData();
  return (
    <Card className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-lg text-danger">Souffre-douleurs de la Horde</h2>
        <span className="text-xs text-muted">morts par des joueurs · ennemis distincts</span>
      </div>
      {victims.length === 0 ? (
        <p className="text-sm text-muted">
          Personne n'est tombé sous les coups d'un joueur sur cette période.
        </p>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {victims.map((v, i) => {
              const isMe = v.user.id === meId;
              return (
                <tr
                  key={v.character.id}
                  className={clsx("border-b border-border/60 last:border-0", isMe && "bg-surface-2/60")}
                >
                  <td className={clsx("w-8 py-1.5 pr-2", i < 3 ? "text-danger" : "text-muted")}>{i + 1}</td>
                  <td className="py-1.5">
                    <Link to={`/personnages/${v.character.id}`}>
                      <CharacterName
                        name={v.character.name}
                        surname={v.character.surname}
                        playerClass={findClass(gamedata.data, v.character.player_class)}
                      />
                    </Link>
                    <span className="text-muted">
                      {" · "}
                      <Link
                        to={`/membres/${v.user.id}`}
                        className={clsx(isMe && "font-medium text-gold-light")}
                      >
                        {isMe ? "toi" : v.user.display_name}
                      </Link>
                    </span>
                    {v.last && (
                      <span className="ml-1 text-[11px] text-muted">dernière fois {shortDate(v.last)}</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap py-1.5 pl-2 text-right font-mono text-danger">
                    {v.deaths}
                  </td>
                  <td className="whitespace-nowrap py-1.5 pl-2 text-right font-mono text-muted">
                    {v.enemies} ennemi{v.enemies > 1 ? "s" : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}
