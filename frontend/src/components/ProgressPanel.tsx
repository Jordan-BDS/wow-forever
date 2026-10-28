import clsx from "clsx";
import { Link } from "react-router";
import type { Character } from "@/api/client";
import { useCharacterProgress, type CharacterProgress } from "@/api/sync";
import { Card, Spinner } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { formatAgo, formatDateTime, formatRemaining } from "@/lib/game";

const SLOT_LABELS: Record<string, string> = {
  head: "Tête",
  neck: "Cou",
  shoulder: "Épaules",
  back: "Dos",
  chest: "Torse",
  shirt: "Chemise",
  tabard: "Tabard",
  wrist: "Poignets",
  hands: "Mains",
  waist: "Taille",
  legs: "Jambes",
  feet: "Pieds",
  finger1: "Doigt",
  finger2: "Doigt",
  trinket1: "Bijou",
  trinket2: "Bijou",
  mainhand: "Main droite",
  offhand: "Main gauche",
  ranged: "À distance",
};
const SLOT_ORDER = Object.keys(SLOT_LABELS);

const ATTUNEMENT_LABELS: Record<string, string> = {
  "molten-core": "Cœur du Magma",
  onyxia: "Repaire d'Onyxia",
  "blackwing-lair": "Repaire de l'Aile noire",
  naxxramas: "Naxxramas",
};

const REACTION_LABELS: Record<number, string> = {
  1: "Haï",
  2: "Hostile",
  3: "Inamical",
  4: "Neutre",
  5: "Amical",
  6: "Honoré",
  7: "Révéré",
  8: "Exalté",
};

function Tile({
  label,
  tile,
  danger,
}: {
  label: string;
  tile: { total: number; week: number };
  danger?: boolean;
}) {
  return (
    <div className="rounded-md border border-border bg-bg/60 p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="font-display text-2xl leading-tight">{tile.total}</div>
      <div
        className={clsx("text-xs", tile.week > 0 ? (danger ? "text-danger" : "text-success") : "text-muted")}
      >
        {tile.week > 0 ? `+${tile.week} cette semaine` : "rien cette semaine"}
      </div>
    </div>
  );
}

export function ProgressPanel({ character }: { character: Character }) {
  const progress = useCharacterProgress(character.id);
  if (progress.isPending) return <Spinner />;
  if (progress.isError || !progress.data)
    return <p className="text-sm text-danger">Impossible de charger la progression.</p>;
  const p = progress.data;
  if (!p.available) {
    return (
      <Card className="text-sm text-muted">
        Rien reçu du jeu pour ce personnage. Avec l'addon et le compagnon, ou un code collé dans{" "}
        <Link to="/profil">ton profil</Link>, cet onglet se remplit tout seul : accès, verrous, boss tués,
        récolte, morts…
      </Card>
    );
  }
  return <ProgressContent character={character} p={p} />;
}

function ProgressContent({ character, p }: { character: Character; p: CharacterProgress }) {
  const tiles = p.tiles!;
  const gathering = p.gathering!;
  const gatheringWeek = p.gathering_week!;
  const gear = [...(p.gear ?? [])].sort((a, b) => SLOT_ORDER.indexOf(a.slot) - SLOT_ORDER.indexOf(b.slot));
  const attunements = Object.entries(p.attunements ?? {});
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
        <span className="text-muted">
          Synchronisé {formatAgo(p.synced_at!)} · compteurs depuis le{" "}
          {p.counting_since ? new Date(p.counting_since).toLocaleDateString("fr-FR") : "?"}
        </span>
        {p.played != null && (
          <span className="text-muted">Temps de jeu : {Math.round(p.played / 3600)} h</span>
        )}
      </div>

      <section>
        <h3 className="mb-2 font-display text-lg">Activité</h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Tile label="Boss tués" tile={tiles.boss_kills} />
          <Tile label="Donjons terminés" tile={tiles.dungeons_done} />
          <Tile label="Raids terminés" tile={tiles.raids_done} />
          <Tile label="Morts" tile={tiles.deaths} danger />
          <Tile label="Champs de bataille" tile={tiles.bg_played} />
          <Tile label="BG gagnés" tile={tiles.bg_won} />
          <Tile label="Quêtes rendues" tile={tiles.quests} />
          <Tile label="Objets fabriqués" tile={tiles.crafted_total} />
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="space-y-2">
          <h3 className="font-display text-lg">Accès aux raids</h3>
          {attunements.length === 0 ? (
            <p className="text-sm text-muted">Pas encore lu.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {attunements.map(([key, done]) => (
                <li key={key} className="flex justify-between gap-2">
                  <span>{ATTUNEMENT_LABELS[key] ?? key}</span>
                  <span className={done ? "text-success" : "text-danger"}>
                    {done ? "Acquis" : "Manquant"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="space-y-2">
          <h3 className="font-display text-lg">Verrous en cours</h3>
          {(p.lockouts ?? []).length === 0 ? (
            <p className="text-sm text-muted">Aucun verrou.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {p.lockouts!.map((lk) => (
                <li key={`${lk.name}-${lk.reset_at}`}>
                  <div className="flex justify-between gap-2">
                    <span>{lk.name}</span>
                    <span className="text-gold-light">
                      {lk.killed} / {lk.bosses} boss
                    </span>
                  </div>
                  {lk.reset_at && (
                    <div className="text-xs text-muted">réinitialisation {formatRemaining(lk.reset_at)}</div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="space-y-2">
          <h3 className="font-display text-lg">Réputations</h3>
          {(p.reputations ?? []).length === 0 ? (
            <p className="text-sm text-muted">Pas encore lu.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {p.reputations!.slice(0, 8).map((r) => (
                <li key={`${r.id}-${r.name}`} className="flex justify-between gap-2">
                  <span className="truncate">{r.name}</span>
                  <span className="shrink-0 text-muted">
                    {r.reaction ? (REACTION_LABELS[r.reaction] ?? r.reaction) : r.value}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="space-y-2">
          <div className="flex items-baseline justify-between">
            <h3 className="font-display text-lg">Récolte</h3>
            <span className="text-xs text-muted">approximatif : sort de récolte + butin</span>
          </div>
          <table className="w-full text-sm">
            <tbody>
              {(
                [
                  ["mining", "Minerais"],
                  ["herbalism", "Herbes"],
                  ["skinning", "Peaux"],
                  ["fishing", "Poissons"],
                ] as const
              ).map(([key, label]) => (
                <tr key={key} className="border-b border-border/60 last:border-0">
                  <td className="py-1">{label}</td>
                  <td className="py-1 text-right font-mono">{gathering[key]}</td>
                  <td
                    className={clsx(
                      "w-20 py-1 text-right text-xs",
                      gatheringWeek[key] > 0 ? "text-success" : "text-muted",
                    )}
                  >
                    {gatheringWeek[key] > 0 ? `+${gatheringWeek[key]}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card className="space-y-2">
          <div className="flex items-baseline justify-between">
            <h3 className="font-display text-lg">PvP</h3>
            <span className="text-xs text-muted">
              {p.pvp?.hk_lifetime != null ? `${p.pvp.hk_lifetime} victoires honorables` : "pas encore lu"}
              {p.pvp?.rank ? ` · rang ${p.pvp.rank}` : ""}
            </span>
          </div>
          {(p.pvp?.battlegrounds ?? []).length === 0 ? (
            <p className="text-sm text-muted">Aucun champ de bataille compté.</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {p.pvp!.battlegrounds.map((bg) => (
                  <tr key={bg.map} className="border-b border-border/60 last:border-0">
                    <td className="py-1">{bg.map}</td>
                    <td className="py-1 text-right font-mono">
                      {bg.won} / {bg.played}
                    </td>
                    <td className="w-16 py-1 text-right text-muted">
                      {bg.played ? `${Math.round((100 * bg.won) / bg.played)} %` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      {(p.bosses ?? []).length > 0 && (
        <Card className="space-y-2">
          <h3 className="font-display text-lg">Boss tués</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted">
                  <th className="py-1 pr-3">Boss</th>
                  <th className="py-1 pr-3 text-right">Kills</th>
                  <th className="py-1 pr-3">Premier</th>
                  <th className="py-1">Dernier</th>
                </tr>
              </thead>
              <tbody>
                {p.bosses!.map((b) => (
                  <tr key={`${b.id}-${b.name}`} className="border-t border-border/60">
                    <td className="py-1 pr-3">{b.name}</td>
                    <td className="py-1 pr-3 text-right font-mono">{b.kills}</td>
                    <td className="py-1 pr-3 text-muted">{b.first ? formatDateTime(b.first) : "—"}</td>
                    <td className="py-1 text-muted">{b.last ? formatDateTime(b.last) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {gear.length > 0 && (
        <Card className="space-y-2">
          <div className="flex items-baseline justify-between">
            <h3 className="font-display text-lg">Porté en jeu</h3>
            <span className="text-xs text-muted">lecture seule, tel que reçu de l'addon</span>
          </div>
          <ul className="grid gap-1 text-sm sm:grid-cols-2">
            {gear.map((g) => (
              <li key={g.slot} className="flex justify-between gap-2">
                <span className="text-muted">{SLOT_LABELS[g.slot] ?? g.slot}</span>
                <span className="truncate text-right">
                  <WowheadLink kind="item" id={g.item_id} quality={g.quality ?? undefined}>
                    {g.name ?? `Objet ${g.item_id}`}
                  </WowheadLink>
                  {g.enchant_id && <span className="ml-1 text-xs text-success">enchanté</span>}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="space-y-2">
          <h3 className="font-display text-lg">Historique</h3>
          {(p.levels ?? []).length > 0 && (
            <p className="text-sm text-muted">
              Montées de niveau enregistrées :{" "}
              {p.levels!.map((l) => `${l.level} (${new Date(l.at).toLocaleDateString("fr-FR")})`).join(", ")}
            </p>
          )}
          {(p.series ?? []).length > 1 ? (
            <Sparkline series={p.series!} />
          ) : (
            <p className="text-sm text-muted">Les courbes apparaîtront après quelques jours de données.</p>
          )}
        </Card>
        <Card className="space-y-2">
          <h3 className="font-display text-lg">Dernières synchronisations</h3>
          <ul className="space-y-1 text-sm">
            {(p.syncs ?? []).map((s) => (
              <li key={s.received_at} className="flex justify-between gap-2">
                <span>{formatDateTime(s.received_at)}</span>
                <span className="text-muted">
                  {s.source === "companion"
                    ? `Compagnon${s.device ? ` · ${s.device}` : ""}`
                    : "Code collé sur le site"}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">
            Niveau et personnage : {character.full_name || character.name}, niveau {character.level}.
          </p>
        </Card>
      </div>
    </div>
  );
}

/** Courbe des morts et des boss par jour, sans bibliothèque : un SVG de 100 × 30. */
function Sparkline({ series }: { series: NonNullable<CharacterProgress["series"]> }) {
  const rows = [
    { key: "deaths" as const, label: "Morts", color: "var(--color-danger)" },
    { key: "boss_kills" as const, label: "Boss", color: "var(--color-gold)" },
    { key: "mining" as const, label: "Minerais", color: "var(--color-success)" },
  ];
  return (
    <div className="space-y-2">
      {rows.map((row) => {
        const values = series.map((s) => s[row.key]);
        const max = Math.max(1, ...values);
        const points = values
          .map((v, i) => `${(100 * i) / Math.max(1, values.length - 1)},${30 - (28 * v) / max + 1}`)
          .join(" ");
        return (
          <div key={row.key} className="flex items-center gap-3 text-xs">
            <span className="w-16 text-muted">{row.label}</span>
            <svg
              viewBox="0 0 100 32"
              className="h-8 flex-1"
              preserveAspectRatio="none"
              role="img"
              aria-label={`${row.label} : ${values[0]} → ${values[values.length - 1]}`}
            >
              <polyline
                fill="none"
                stroke={row.color}
                strokeWidth="2"
                vectorEffect="non-scaling-stroke"
                points={points}
              />
            </svg>
            <span className="w-12 text-right font-mono">{values[values.length - 1]}</span>
          </div>
        );
      })}
      <div className="text-xs text-muted">
        du {new Date(series[0].day).toLocaleDateString("fr-FR")} au{" "}
        {new Date(series[series.length - 1].day).toLocaleDateString("fr-FR")}
      </div>
    </div>
  );
}
