import { useState, type FormEvent } from "react";
import clsx from "clsx";
import {
  categoryPath,
  formatChange,
  formatMoney,
  useAuctions,
  useSetFavoriteItem,
  useSetItemAlerts,
  type AuctionCategory,
  type AuctionOrder,
  type AuctionRow,
  type AuctionSince,
  type AuctionSort,
} from "@/api/auctions";
import { errorMessage } from "@/api/client";
import { ItemPriceHistory } from "@/components/PriceChart";
import { Button, Card, Input, PageTitle, Pill, Select, PageSkeleton } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { formatDateTime } from "@/lib/game";
import { useDebounced } from "@/lib/useDebounced";
import { useWowheadTooltips } from "@/lib/wowhead";

const SINCE: { value: AuctionSince; label: string }[] = [
  { value: "prev", label: "Scan précédent" },
  { value: "day", label: "24 h" },
  { value: "week", label: "7 jours" },
];

/** Les tris sans colonne à cliquer ; le nom, le nombre d'enchères et le prix se trient par l'en-tête de la liste. */
const SORTS: { value: AuctionSort; label: string }[] = [
  { value: "up", label: "Plus fortes hausses" },
  { value: "down", label: "Plus fortes baisses" },
  { value: "sold", label: "Enchères parties" },
  { value: "posted", label: "Enchères arrivées" },
];

const isMovement = (sort: AuctionSort) => sort === "sold" || sort === "posted";

/** Prix de l'hôtel des ventes scannés en jeu et envoyés par le compagnon des membres. */
export function AuctionsPage() {
  const [house, setHouse] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<AuctionSort>("name");
  const [order, setOrder] = useState<AuctionOrder>("asc");
  const [since, setSince] = useState<AuctionSince>("prev");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const [onFavorites, setOnFavorites] = useState(false);
  const q = useDebounced(query.trim());
  const auctions = useAuctions(
    { house, q, sort, order, since, page, category, favorites: onFavorites },
    true,
  );
  const setFavorite = useSetFavoriteItem();
  useWowheadTooltips([auctions.data]);

  if (auctions.isError) return <p className="text-sm text-danger">Impossible de charger les prix.</p>;
  if (!auctions.data) return <PageSkeleton />;
  const data = auctions.data;

  if (!data.scan) {
    return (
      <>
        <PageTitle>Hôtel des ventes</PageTitle>
        <Card className="space-y-2 text-sm text-muted">
          <p>Aucun scan reçu pour l'instant.</p>
          <p>
            En jeu, ouvre l'hôtel des ventes et lance « Scan Prices » (addon NaowhForever) ou un scan complet
            d'Auctionator, puis fais /reload ou déconnecte-toi : ton compagnon envoie le scan tout seul.
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

  const houses = data.houses.length > 1 && (
    <div className="mb-4 flex justify-end">
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
    </div>
  );

  /** Clic sur un en-tête : la colonne déjà triée change de sens, une autre part de A à Z ou du moins cher. */
  const sortBy = (column: AuctionSort) =>
    change(() => {
      setOrder(sort === column && order === "asc" ? "desc" : "asc");
      setSort(column);
    });
  const header = (column: AuctionSort, label: string) => (
    <SortHeader label={label} order={sort === column ? order : null} onClick={() => sortBy(column)} />
  );

  const path = categoryPath(data.categories, category);
  const pick = (key: string) => change(() => setCategory(key));

  return (
    <>
      <PageTitle>Hôtel des ventes</PageTitle>
      {houses}
      <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start">
        <Card className="hidden p-2 lg:block">
          <CategoryTree categories={data.categories} path={path} onPick={pick} />
        </Card>
        {/* Écran étroit : le même arbre, replié sous le type retenu. */}
        <Card className="p-2 lg:hidden">
          <details>
            <summary className="cursor-pointer px-2 py-1 text-sm">
              <span className="text-muted">Type d'objet : </span>
              {path.length ? path.map((c) => c.label).join(" › ") : "tous"}
            </summary>
            <div className="mt-2">
              <CategoryTree categories={data.categories} path={path} onPick={pick} />
            </div>
          </details>
        </Card>
        <div className="min-w-0">
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
              <span className="text-muted">Afficher</span>
              <Pill active={!onFavorites} onClick={() => change(() => setOnFavorites(false))}>
                Tous les objets
              </Pill>
              <Pill active={onFavorites} onClick={() => change(() => setOnFavorites(true))}>
                {data.favorites > 0 ? `★ Mes favoris (${data.favorites})` : "★ Mes favoris"}
              </Pill>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted">Variation depuis</span>
              {SINCE.map((s) => (
                <Pill
                  key={s.value}
                  active={since === s.value}
                  onClick={() => change(() => setSince(s.value))}
                >
                  {s.label}
                </Pill>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted">Classer par</span>
              {SORTS.map((s) => (
                <Pill
                  key={s.value}
                  active={sort === s.value}
                  // Recliquer le classement retenu revient au tri par nom.
                  onClick={() =>
                    change(() => {
                      setSort(sort === s.value ? "name" : s.value);
                      setOrder("asc");
                    })
                  }
                >
                  {s.label}
                </Pill>
              ))}
            </div>
            <p className="text-xs text-muted">
              {data.house} · dernier scan le {formatDateTime(data.scan.scanned_at)} ({data.scan.items} objets)
              ·{" "}
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
                    : onFavorites && data.favorites === 0
                      ? "Aucun objet favori : clique l'étoile d'un objet pour le suivre."
                      : path.length && !q
                        ? "Aucun objet de ce type en vente."
                        : "Aucun objet ne correspond."}
              </p>
            ) : (
              <ul className="divide-y divide-border/60">
                <li className="flex items-center gap-3 px-3 py-2 text-xs">
                  <div className="flex min-w-0 flex-1 items-center gap-4">
                    {header("name", "Objet")}
                    {header("listed", "Enchères")}
                  </div>
                  {header("price", "Prix")}
                  {/* La place des boutons d'une ligne, pour que « Prix » tombe au-dessus des prix. */}
                  <div aria-hidden="true" className="invisible flex items-center gap-3">
                    <span className="border px-2">Historique</span>
                    <span className="border px-2">Alertes</span>
                    <span className="text-xl leading-none">☆</span>
                  </div>
                </li>
                {data.results.map((row) => (
                  <AuctionItem
                    key={row.item_id}
                    row={row}
                    house={data.house}
                    movement={isMovement(sort)}
                    open={open === row.item_id}
                    onToggle={() => setOpen(open === row.item_id ? null : row.item_id)}
                    busy={setFavorite.isPending}
                    onFavorite={() => setFavorite.mutate({ itemId: row.item_id, favorite: !row.favorite })}
                  />
                ))}
              </ul>
            )}
          </Card>
          {setFavorite.isError && (
            <p className="mt-2 text-sm text-danger">Le favori n'a pas pu être changé.</p>
          )}

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
        </div>
      </div>
    </>
  );
}

/** Un en-tête de colonne cliquable, comme dans un tableau : la flèche dit le sens du tri en cours. */
function SortHeader({
  label,
  order,
  onClick,
}: {
  label: string;
  /** Null si la liste n'est pas triée par cette colonne. */
  order: AuctionOrder | null;
  onClick: () => void;
}) {
  const next = order === "asc" ? "décroissant" : "croissant";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`${label} : trier en ordre ${next}`}
      aria-pressed={order != null}
      className={clsx(
        "flex items-center gap-1 font-semibold uppercase tracking-wide transition-colors",
        order ? "text-gold-light" : "text-muted hover:text-text",
      )}
    >
      {label}
      <span aria-hidden="true" className={order ? undefined : "opacity-40"}>
        {order === "asc" ? "▲" : order === "desc" ? "▼" : "↕"}
      </span>
    </button>
  );
}

/** Les types d'objets, comme le panneau de gauche de l'hôtel des ventes en jeu : seule la branche retenue est
 * dépliée. Cliquer le type déjà retenu revient à son parent. */
function CategoryTree({
  categories,
  path,
  onPick,
}: {
  categories: AuctionCategory[];
  /** Du type le plus large au type retenu, vide si aucun. */
  path: AuctionCategory[];
  onPick: (key: string) => void;
}) {
  const selected = path.at(-1)?.key ?? "";
  const row = (active: boolean, depth: number) =>
    clsx(
      "block w-full rounded-sm py-1 pr-2 text-left text-sm transition-colors",
      depth === 0 ? "pl-2" : depth === 1 ? "pl-5" : "pl-8",
      active ? "bg-surface-2 text-gold-light" : "text-muted hover:bg-surface-2/60 hover:text-text",
    );
  const branch = (nodes: AuctionCategory[], depth: number, parent: string) => (
    <ul className="space-y-0.5">
      {nodes.map((node) => {
        const open = path[depth]?.key === node.key;
        return (
          <li key={node.key}>
            <button
              type="button"
              aria-current={selected === node.key ? "true" : undefined}
              aria-expanded={node.children.length ? open : undefined}
              className={row(selected === node.key, depth)}
              onClick={() => onPick(selected === node.key ? parent : node.key)}
            >
              {node.label}
            </button>
            {open && node.children.length > 0 && branch(node.children, depth + 1, node.key)}
          </li>
        );
      })}
    </ul>
  );
  return (
    <nav aria-label="Type d'objet">
      <button type="button" className={row(selected === "", 0)} onClick={() => onPick("")}>
        Tous les types
      </button>
      {branch(categories, 0, "")}
    </nav>
  );
}

function AuctionItem({
  row,
  house,
  movement,
  open,
  onToggle,
  busy,
  onFavorite,
}: {
  row: AuctionRow;
  house: string;
  /** Tri de mouvements : la colonne de droite montre les enchères parties ou arrivées et leur valeur. */
  movement: boolean;
  open: boolean;
  onToggle: () => void;
  busy: boolean;
  onFavorite: () => void;
}) {
  const [alerts, setAlerts] = useState(false);
  const below = !row.gone && row.buy_price != null && row.price <= row.buy_price;
  const above = !row.gone && row.sell_price != null && row.price >= row.sell_price;
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
          {(row.buy_price != null || row.sell_price != null) && (
            <div className="flex flex-wrap gap-x-3 text-xs text-muted">
              {row.buy_price != null && (
                <span className={below ? "font-semibold text-success" : undefined}>
                  {below ? "à ton prix d'achat ou en dessous" : "achat"} : {formatMoney(row.buy_price)}
                </span>
              )}
              {row.sell_price != null && (
                <span className={above ? "font-semibold text-gold" : undefined}>
                  {above ? "à ton prix de vente ou au-dessus" : "vente"} : {formatMoney(row.sell_price)}
                </span>
              )}
            </div>
          )}
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
        <button
          type="button"
          onClick={() => setAlerts(!alerts)}
          aria-expanded={alerts}
          className="rounded-sm border border-border px-2 py-1 text-xs text-muted hover:border-gold hover:text-gold"
        >
          {alerts ? "Fermer" : "Alertes"}
        </button>
        <button
          type="button"
          onClick={onFavorite}
          disabled={busy}
          aria-pressed={row.favorite}
          title={row.favorite ? "Retirer des favoris" : "Ajouter aux favoris"}
          className={clsx(
            "text-xl leading-none transition-colors disabled:opacity-50",
            row.favorite ? "text-gold hover:text-gold-light" : "text-muted hover:text-gold",
          )}
        >
          {row.favorite ? "★" : "☆"}
        </button>
      </div>
      {alerts && <AlertEditor row={row} onDone={() => setAlerts(false)} />}
      {open && (
        <div className="px-3 pb-4">
          <ItemPriceHistory
            itemId={row.item_id}
            house={house}
            thresholds={{ buy: row.buy_price, sell: row.sell_price }}
          />
        </div>
      )}
    </li>
  );
}

type Coins = { po: string; pa: string; pc: string };

const toCoins = (copper: number | null): Coins =>
  copper == null
    ? { po: "", pa: "", pc: "" }
    : {
        po: String(Math.floor(copper / 10000) || ""),
        pa: String(Math.floor(copper / 100) % 100 || ""),
        pc: String(copper % 100 || ""),
      };

/** Null si les trois cases sont vides ou nulles : pas de seuil. */
const toCopper = (coins: Coins): number | null =>
  (Number(coins.po) || 0) * 10000 + (Number(coins.pa) || 0) * 100 + (Number(coins.pc) || 0) || null;

/** Les deux seuils d'un objet : le bot Discord écrit en MP quand le prix le plus bas en franchit un. */
function AlertEditor({ row, onDone }: { row: AuctionRow; onDone: () => void }) {
  const [buy, setBuy] = useState(toCoins(row.buy_price));
  const [sell, setSell] = useState(toCoins(row.sell_price));
  const save = useSetItemAlerts();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(
      { itemId: row.item_id, buy_price: toCopper(buy), sell_price: toCopper(sell) },
      { onSuccess: onDone },
    );
  };
  return (
    <form onSubmit={submit} className="space-y-2 px-3 pb-4 text-xs text-muted">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
        <CoinsInput label="Prix d'achat : m'écrire à ce prix ou en dessous" value={buy} onChange={setBuy} />
        <CoinsInput label="Prix de vente : m'écrire à ce prix ou au-dessus" value={sell} onChange={setSell} />
        <Button type="submit" disabled={save.isPending} className="px-3 py-1.5 text-xs">
          Enregistrer
        </Button>
      </div>
      <p>
        Prix le plus bas à l'unité. Le bot Discord t'écrit en MP quand un scan franchit un seuil, une fois par
        franchissement ; cases vides : pas d'alerte.{!row.favorite && " Enregistrer suit l'objet."}
      </p>
      {save.isError && <p className="text-danger">{errorMessage(save.error)}</p>}
    </form>
  );
}

function CoinsInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: Coins;
  onChange: (value: Coins) => void;
}) {
  const units = [
    ["po", "po", 99999],
    ["pa", "pa", 99],
    ["pc", "pc", 99],
  ] as const;
  return (
    <fieldset>
      <legend className="mb-1">{label}</legend>
      <div className="flex items-center gap-1.5">
        {units.map(([key, unit, max]) => (
          <label key={key} className="flex items-center gap-1">
            <Input
              type="number"
              min={0}
              max={max}
              step={1}
              inputMode="numeric"
              value={value[key]}
              onChange={(e) => onChange({ ...value, [key]: e.target.value })}
              className={key === "po" ? "w-20 px-2 py-1 text-right" : "w-14 px-2 py-1 text-right"}
            />
            {unit}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
