import { useState } from "react";
import { Navigate, useSearchParams } from "react-router";
import clsx from "clsx";
import {
  formatChange,
  formatMoney,
  useAuctions,
  type AuctionRow,
  type AuctionSince,
  type AuctionSort,
} from "@/api/auctions";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { ItemPriceHistory } from "@/components/PriceChart";
import { RecipeCosts } from "@/components/RecipeCosts";
import { Card, Input, PageTitle, Pill, Select, Spinner } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { formatDateTime } from "@/lib/game";
import { useDebounced } from "@/lib/useDebounced";
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
  { value: "sold", label: "Enchères parties" },
  { value: "posted", label: "Enchères arrivées" },
];

const isMovement = (sort: AuctionSort) => sort === "sold" || sort === "posted";

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
  const [params, setParams] = useSearchParams();
  const onRecipes = params.get("onglet") === "recettes";
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

  const tabs = (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap gap-2">
        <Pill active={!onRecipes} onClick={() => setParams({}, { replace: true })}>
          Tous les objets
        </Pill>
        <Pill active={onRecipes} onClick={() => setParams({ onglet: "recettes" }, { replace: true })}>
          Recettes favorites
        </Pill>
      </div>
      {data.houses.length > 1 && (
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted">Hôtel des ventes</span>
          <Select value={data.house} onChange={(e) => change(() => setHouse(e.target.value))}>
            {data.houses.map((h) => (
              <option key={h.house} value={h.house}>
                {h.house}
              </option>
            ))}
          </Select>
        </label>
      )}
    </div>
  );

  if (onRecipes) {
    return (
      <>
        <PageTitle>Hôtel des ventes</PageTitle>
        {tabs}
        <RecipeCosts house={data.house} />
      </>
    );
  }

  return (
    <>
      <PageTitle>Hôtel des ventes</PageTitle>
      {tabs}
      <Card className="mb-4 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex-1 text-sm">
            <span className="text-muted">Objet (nom français ou anglais, ou ID)</span>
            <Input
              value={query}
              placeholder="Ex. Étoffe de lin"
              onChange={(e) => change(() => setQuery(e.target.value))}
            />
          </label>
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
        {isMovement(sort) && (
          <p className="text-xs text-muted">
            Estimation d'après le nombre d'enchères des deux scans : une enchère partie a pu être vendue,
            annulée ou avoir expiré. Valeur comptée au prix le plus bas, une unité par enchère.
          </p>
        )}
      </Card>

      <Card className="p-0">
        {data.results.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted">
            {sort === "up" || sort === "down"
              ? "Aucune variation à montrer : il faut un scan de référence."
              : isMovement(sort)
                ? "Aucun mouvement à montrer entre ces deux scans."
                : "Aucun objet ne correspond."}
          </p>
        ) : (
          <ul className="divide-y divide-border/60">
            {data.results.map((row) => (
              <AuctionItem
                key={row.item_id}
                row={row}
                house={data.house}
                movement={isMovement(sort)}
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
  movement,
  open,
  onToggle,
}: {
  row: AuctionRow;
  house: string;
  /** Tri de mouvements : la colonne de droite montre les enchères parties ou arrivées et leur valeur. */
  movement: boolean;
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
            {row.gone
              ? `plus en vente · ${row.previous_listed} enchère${(row.previous_listed ?? 0) > 1 ? "s" : ""} avant`
              : row.listed == null
                ? "nombre d'enchères inconnu"
                : movement && row.previous_listed != null
                  ? `${row.previous_listed} → ${row.listed} enchère${row.listed > 1 ? "s" : ""}`
                  : `${row.listed} enchère${row.listed > 1 ? "s" : ""}`}
          </div>
        </div>
        {movement && row.listed_change != null && (
          <div className="text-right">
            <div className={clsx("font-mono", row.listed_change < 0 ? "text-danger" : "text-success")}>
              {row.listed_change > 0 ? "+" : "−"}
              {Math.abs(row.listed_change)}
            </div>
            <div className="text-xs text-muted">≈ {formatMoney(row.moved ?? 0)}</div>
          </div>
        )}
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
            {row.gone ? "dernier prix" : row.change == null ? "nouveau" : formatChange(row.change)}
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
      {open && (
        <div className="px-3 pb-4">
          <ItemPriceHistory itemId={row.item_id} house={house} />
        </div>
      )}
    </li>
  );
}
