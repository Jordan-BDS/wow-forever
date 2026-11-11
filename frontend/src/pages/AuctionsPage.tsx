import { useEffect, useState } from "react";
import { Navigate } from "react-router";
import clsx from "clsx";
import {
  formatChange,
  formatMoney,
  useAuctionHistory,
  useAuctions,
  type AuctionRow,
  type AuctionSince,
  type AuctionSort,
} from "@/api/auctions";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Card, Input, PageTitle, Pill, Select, Spinner } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { formatDateTime } from "@/lib/game";
import { useWowheadTooltips } from "@/lib/wowhead";

const SINCE: { value: AuctionSince; label: string }[] = [
  { value: "prev", label: "Scan précédent" },
  { value: "day", label: "24 h" },
  { value: "week", label: "7 jours" },
];

const SORTS: { value: AuctionSort; label: string }[] = [
  { value: "name", label: "Nom" },
  { value: "price", label: "Prix" },
  { value: "listed", label: "Enchères" },
  { value: "up", label: "Plus fortes hausses" },
  { value: "down", label: "Plus fortes baisses" },
];

function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

/** Prix de l'hôtel des ventes scannés en jeu et envoyés par le compagnon : réservé au GM. */
export function AuctionsPage() {
  const me = useCurrentUser();
  const isGm = me.site_role === "gm";
  const [house, setHouse] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<AuctionSort>("name");
  const [since, setSince] = useState<AuctionSince>("prev");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const q = useDebounced(query.trim());
  const auctions = useAuctions({ house, q, sort, since, page }, isGm);
  useWowheadTooltips([auctions.data]);

  if (!isGm) return <Navigate to="/roster" replace />;
  if (auctions.isError) return <p className="text-sm text-danger">Impossible de charger les prix.</p>;
  if (!auctions.data) return <Spinner />;
  const data = auctions.data;

  if (!data.scan) {
    return (
      <>
        <PageTitle>Hôtel des ventes</PageTitle>
        <Card className="space-y-2 text-sm text-muted">
          <p>Aucun scan reçu pour l'instant.</p>
          <p>
            En jeu, ouvre l'hôtel des ventes et lance « Scan Prices » (addon NaowhForever), puis fais /reload
            ou déconnecte-toi : ton compagnon envoie le scan tout seul.
          </p>
        </Card>
      </>
    );
  }

  const change = (patch: () => void) => {
    patch();
    setPage(1);
    setOpen(null);
  };

  return (
    <>
      <PageTitle>Hôtel des ventes</PageTitle>
      <Card className="mb-4 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex-1 text-sm">
            <span className="text-muted">Objet (nom ou ID)</span>
            <Input
              value={query}
              placeholder="Ex. Étoffe de lin"
              onChange={(e) => change(() => setQuery(e.target.value))}
            />
          </label>
          {data.houses.length > 1 && (
            <label className="text-sm">
              <span className="text-muted">Hôtel des ventes</span>
              <Select
                className="block w-full"
                value={data.house}
                onChange={(e) => change(() => setHouse(e.target.value))}
              >
                {data.houses.map((h) => (
                  <option key={h.house} value={h.house}>
                    {h.house}
                  </option>
                ))}
              </Select>
            </label>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">Variation depuis</span>
          {SINCE.map((s) => (
            <Pill key={s.value} active={since === s.value} onClick={() => change(() => setSince(s.value))}>
              {s.label}
            </Pill>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">Trier par</span>
          {SORTS.map((s) => (
            <Pill key={s.value} active={sort === s.value} onClick={() => change(() => setSort(s.value))}>
              {s.label}
            </Pill>
          ))}
        </div>
        <p className="text-xs text-muted">
          {data.house} · dernier scan le {formatDateTime(data.scan.scanned_at)} ({data.scan.items} objets) ·{" "}
          {data.baseline
            ? `comparé au scan du ${formatDateTime(data.baseline.scanned_at)}`
            : since === "prev"
              ? "pas encore de scan plus ancien : les variations arriveront au prochain"
              : "pas de scan assez ancien pour cette période"}
        </p>
      </Card>

      <Card className="p-0">
        {data.results.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted">
            {sort === "up" || sort === "down"
              ? "Aucune variation à montrer : il faut un scan de référence."
              : "Aucun objet ne correspond."}
          </p>
        ) : (
          <ul className="divide-y divide-border/60">
            {data.results.map((row) => (
              <AuctionItem
                key={row.item_id}
                row={row}
                house={data.house}
                open={open === row.item_id}
                onToggle={() => setOpen(open === row.item_id ? null : row.item_id)}
              />
            ))}
          </ul>
        )}
      </Card>

      {data.pages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3 text-sm">
          <Pill active={false} onClick={() => setPage(Math.max(1, data.page - 1))}>
            Précédent
          </Pill>
          <span className="text-muted">
            Page {data.page} / {data.pages} · {data.total} objets
          </span>
          <Pill active={false} onClick={() => setPage(Math.min(data.pages, data.page + 1))}>
            Suivant
          </Pill>
        </div>
      )}
    </>
  );
}

function AuctionItem({
  row,
  house,
  open,
  onToggle,
}: {
  row: AuctionRow;
  house: string;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <li className="text-sm">
      <div className="flex items-center gap-3 px-3 py-2">
        {row.icon_url ? (
          <img src={row.icon_url} alt="" className="size-9 rounded border border-border" loading="lazy" />
        ) : (
          <div className="size-9 rounded border border-border bg-bg" />
        )}
        <div className="min-w-0 flex-1">
          <WowheadLink
            kind="item"
            id={row.item_id}
            quality={row.quality}
            className="font-medium hover:underline"
          >
            {row.name}
          </WowheadLink>
          <div className="text-xs text-muted">
            {row.listed != null
              ? `${row.listed} enchère${row.listed > 1 ? "s" : ""}`
              : "nombre d'enchères inconnu"}
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono">{formatMoney(row.price)}</div>
          <div
            className={clsx(
              "text-xs",
              row.change == null || row.change === 0
                ? "text-muted"
                : row.change > 0
                  ? "text-success"
                  : "text-danger",
            )}
            title={row.previous_price != null ? `avant : ${formatMoney(row.previous_price)}` : undefined}
          >
            {row.change == null ? "nouveau" : formatChange(row.change)}
          </div>
        </div>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="rounded-sm border border-border px-2 py-1 text-xs text-muted hover:border-gold hover:text-gold"
        >
          {open ? "Fermer" : "Historique"}
        </button>
      </div>
      {open && <History itemId={row.item_id} house={house} />}
    </li>
  );
}

function History({ itemId, house }: { itemId: number; house: string }) {
  const history = useAuctionHistory(itemId, house);
  if (history.isError) return <p className="px-3 pb-3 text-xs text-danger">Historique indisponible.</p>;
  if (!history.data) {
    return (
      <div className="px-3 pb-3">
        <Spinner />
      </div>
    );
  }
  const { points, min, max, average } = history.data;
  if (points.length < 2 || min == null || max == null || average == null) {
    return (
      <p className="px-3 pb-3 text-xs text-muted">
        Un seul scan pour cet objet : la courbe apparaîtra au prochain scan où il sera en vente.
      </p>
    );
  }
  const first = new Date(points[0].at).getTime();
  const span = Math.max(1, new Date(points[points.length - 1].at).getTime() - first);
  const range = Math.max(1, max - min);
  const line = points
    .map((p) => {
      const x = (100 * (new Date(p.at).getTime() - first)) / span;
      const y = 38 - (36 * (p.price - min)) / range;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <div className="space-y-1 px-3 pb-3 text-xs text-muted">
      <svg
        viewBox="0 0 100 40"
        className="h-24 w-full rounded-sm border border-border/60 bg-bg/60"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Prix de ${formatMoney(points[0].price)} à ${formatMoney(points[points.length - 1].price)} sur ${points.length} scans`}
      >
        <polyline
          fill="none"
          stroke="var(--color-gold)"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
          points={line}
        />
      </svg>
      <div className="flex flex-wrap justify-between gap-x-4">
        <span>
          du {formatDateTime(points[0].at)} au {formatDateTime(points[points.length - 1].at)} ·{" "}
          {points.length} scans
        </span>
        <span>
          min {formatMoney(min)} · moyenne {formatMoney(average)} · max {formatMoney(max)}
        </span>
      </div>
    </div>
  );
}
