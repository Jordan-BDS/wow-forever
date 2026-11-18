import { useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  formatChange,
  formatMoney,
  niceTicks,
  useAuctionHistory,
  type AuctionHistory,
  type AuctionRoundTrip,
  type AuctionTrade,
} from "@/api/auctions";
import { Pill, Spinner } from "@/components/ui";
import { formatDateTime } from "@/lib/game";

type Point = AuctionHistory["points"][number];
type Timed = Point & { t: number };
type Period = [number, number]; // début et fin, en millisecondes
type Range = "day" | "three" | "week" | "month" | "all";

const RANGES: { value: Range; label: string; days: number | null }[] = [
  { value: "day", label: "24 h", days: 1 },
  { value: "three", label: "3 jours", days: 3 },
  { value: "week", label: "7 jours", days: 7 },
  { value: "month", label: "30 jours", days: 30 },
  { value: "all", label: "Tout", days: null },
];

const DAY = 86_400_000;
const MARGIN = { top: 10, right: 16, bottom: 24, left: 92 };
const PRICE_COLOR = "var(--color-gold)";
const LISTED_COLOR = "#8fb0ea";
const BUY_COLOR = "var(--color-success)";
const SELL_COLOR = "var(--color-danger)";

/** Les seuils du joueur sur l'objet, en cuivre : tracés en travers de la courbe des prix. */
type Thresholds = { buy: number | null; sell: number | null };
const MAX_DOTS = 40; // au-delà, les points se touchent : la ligne seule

const dayFormat = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
const hourFormat = new Intl.DateTimeFormat("fr-FR", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function useWidth() {
  // Une référence par fonction : le cadre mesuré disparaît et revient (période sans scan), l'effet doit le suivre.
  const [element, ref] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(640);
  useLayoutEffect(() => {
    if (!element) return;
    if (element.clientWidth) setWidth(element.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width) setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return [ref, width] as const;
}

/** Historique d'un objet dans un hôtel des ventes : chargé à l'ouverture, puis tracé. */
export function ItemPriceHistory({
  itemId,
  house,
  thresholds,
}: {
  itemId: number;
  house: string;
  thresholds?: Thresholds;
}) {
  const history = useAuctionHistory(itemId, house);
  if (history.isError) return <p className="text-xs text-danger">Historique indisponible.</p>;
  if (!history.data) return <Spinner />;
  const { points, trades = [], round_trips: trips = [], trade_summary: summary } = history.data;
  return (
    <div className="space-y-4">
      <PriceHistory points={points} thresholds={thresholds} trades={trades} trips={trips} />
      {summary && <TradeRecap trades={trades} trips={trips} summary={summary} />}
    </div>
  );
}

/** « 40 min », « 5 h », « 3 j 4 h ». */
function formatDuration(seconds: number): string {
  const minutes = Math.max(0, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h`;
  return hours % 24 ? `${Math.floor(hours / 24)} j ${hours % 24} h` : `${hours / 24} j`;
}

const signed = (copper: number) =>
  `${copper > 0 ? "+" : copper < 0 ? "−" : ""}${formatMoney(Math.abs(copper))}`;
const gainClass = (copper: number) =>
  copper > 0 ? "text-success" : copper < 0 ? "text-danger" : "text-text";

function tradeLabel(trade: AuctionTrade): string {
  const what = trade.kind === "buy" ? "Achat" : "Vente";
  const amount =
    trade.quantity != null && trade.price != null
      ? `${trade.quantity} × ${formatMoney(trade.price)}, total ${formatMoney(trade.total)}`
      : `total ${formatMoney(trade.total)}, quantité inconnue`;
  return `${what} du ${formatDateTime(trade.at)} : ${amount}`;
}

/**
 * Mes achats et ventes de l'objet sous sa courbe : le bilan des reventes (chaque vente rapprochée de mes achats
 * les plus anciens encore en stock, commission déduite), puis la liste complète.
 */
export function TradeRecap({
  trades,
  trips,
  summary,
}: {
  trades: AuctionTrade[];
  trips: AuctionRoundTrip[];
  summary: NonNullable<AuctionHistory["trade_summary"]>;
}) {
  const buys = trades.filter((t) => t.kind === "buy").length;
  const cell = "px-2 py-1";
  return (
    <section className="space-y-2 text-xs text-muted" aria-label="Mes achats et ventes">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold text-text">Mes achats et ventes</h4>
        <span>notés par l'addon, visibles par toi seul</span>
      </div>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Achats" value={String(buys)} />
        <Stat label="Ventes" value={String(trades.length - buys)} />
        <Stat label="Bénéfice des reventes" value={summary.trips ? signed(summary.profit) : "aucune"}>
          {summary.trips > 0 && `${summary.trips} revente${summary.trips > 1 ? "s" : ""}, commission déduite`}
        </Stat>
        <Stat label="Acheté, pas revendu" value={String(summary.stock)}>
          {summary.stock > 0 && `payé ${formatMoney(summary.stock_cost)}`}
        </Stat>
      </dl>
      {trips.length > 0 && (
        <div className="max-h-64 overflow-auto rounded-sm border border-border/60">
          <table className="w-full text-left whitespace-nowrap">
            <caption className="sr-only">Mes reventes, la plus récente d'abord</caption>
            <thead className="sticky top-0 bg-surface text-muted">
              <tr>
                <th className={`${cell} font-normal`}>Acheté</th>
                <th className={`${cell} font-normal`}>Revendu</th>
                <th className={`${cell} text-right font-normal`}>Quantité</th>
                <th className={`${cell} text-right font-normal`}>Achat, pièce</th>
                <th className={`${cell} text-right font-normal`}>Vente, pièce</th>
                <th className={`${cell} text-right font-normal`}>Bénéfice</th>
                <th className={`${cell} text-right font-normal`}>Durée</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {[...trips].reverse().map((trip) => (
                <tr key={trip.sale}>
                  <td className={cell}>{formatDateTime(trip.bought_at)}</td>
                  <td className={cell}>{formatDateTime(trip.sold_at)}</td>
                  <td className={`${cell} text-right text-text`}>
                    {trip.quantity}
                    {trip.quantity < trip.sold && ` sur ${trip.sold}`}
                  </td>
                  <td className={`${cell} text-right font-mono text-text`}>{formatMoney(trip.buy_price)}</td>
                  <td className={`${cell} text-right font-mono text-text`}>{formatMoney(trip.sell_price)}</td>
                  <td className={`${cell} text-right font-mono ${gainClass(trip.profit)}`}>
                    {signed(trip.profit)}
                    {trip.margin != null && ` (${formatChange(trip.margin)})`}
                  </td>
                  <td className={`${cell} text-right`}>{formatDuration(trip.seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <details>
        <summary className="cursor-pointer hover:text-text">Voir toutes mes transactions</summary>
        <div className="mt-2 max-h-56 overflow-auto rounded-sm border border-border/60">
          <table className="w-full text-left whitespace-nowrap">
            <thead className="sticky top-0 bg-surface text-muted">
              <tr>
                <th className={`${cell} font-normal`}>Le</th>
                <th className={`${cell} font-normal`}>Sens</th>
                <th className={`${cell} text-right font-normal`}>Quantité</th>
                <th className={`${cell} text-right font-normal`}>Pièce</th>
                <th className={`${cell} text-right font-normal`}>Total</th>
                <th className={`${cell} text-right font-normal`}>Commission</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {[...trades].reverse().map((trade) => (
                <tr key={trade.id}>
                  <td className={cell}>{formatDateTime(trade.at)}</td>
                  <td className={cell} style={{ color: trade.kind === "buy" ? BUY_COLOR : SELL_COLOR }}>
                    {trade.kind === "buy" ? "▲ achat" : "▼ vente"}
                  </td>
                  <td className={`${cell} text-right text-text`}>{trade.quantity ?? "?"}</td>
                  <td className={`${cell} text-right font-mono text-text`}>
                    {trade.price != null ? formatMoney(trade.price) : "?"}
                  </td>
                  <td className={`${cell} text-right font-mono text-text`}>{formatMoney(trade.total)}</td>
                  <td className={`${cell} text-right font-mono`}>
                    {trade.kind === "sell" ? formatMoney(trade.fee) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

/** Courbe du prix le plus bas et du nombre d'enchères d'un objet, scan après scan. Les seuils du joueur, s'il
 * en a, la traversent : prix d'achat en vert, prix de vente en rouge. Ses achats (▲ vert) et ses ventes (▼ rouge)
 * y sont posés à leur prix à l'unité, un trait reliant chaque revente à son achat. */
export function PriceHistory({
  points,
  thresholds,
  trades = [],
  trips = [],
}: {
  points: Point[];
  thresholds?: Thresholds;
  trades?: AuctionTrade[];
  trips?: AuctionRoundTrip[];
}) {
  // La période affichée : null = tout l'historique. Les raccourcis et la réglette du bas la changent tous les deux.
  const [period, setPeriod] = useState<Period | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [ref, width] = useWidth();

  const all = useMemo(() => points.map((p) => ({ ...p, t: new Date(p.at).getTime() })), [points]);
  const start = all.length ? all[0].t : 0;
  const end = all.length ? all[all.length - 1].t : 0;
  const visible = useMemo(
    () => (period ? all.filter((p) => p.t >= period[0] && p.t <= period[1]) : all),
    [all, period],
  );
  // Compté depuis le dernier scan, pas depuis aujourd'hui.
  const preset = (days: number | null): Period | null =>
    days == null || end - days * DAY <= start ? null : [end - days * DAY, end];
  const choose = (next: Period | null) => {
    setPeriod(next && next[0] <= start && next[1] >= end ? null : next);
    setHover(null);
  };

  if (all.length < 2) {
    return (
      <p className="text-xs text-muted">
        {all.length === 0
          ? "Cet objet n'a encore été vu en vente dans aucun scan."
          : "Un seul scan pour cet objet : la courbe apparaîtra au prochain scan où il sera en vente."}
      </p>
    );
  }

  const ranges = (
    <div className="flex flex-wrap items-center gap-2">
      {RANGES.filter((r) => r.days == null || end - r.days * DAY > start).map((r) => {
        const target = preset(r.days);
        return (
          <Pill
            key={r.value}
            active={target ? period?.[0] === target[0] && period?.[1] === target[1] : period == null}
            onClick={() => choose(target)}
          >
            {r.label}
          </Pill>
        );
      })}
    </div>
  );
  // La clé garde la même réglette quand la courbe disparaît ou revient : sans elle, le glissement en cours se perd.
  const brush = <Brush key="brush" width={width} points={all} period={period} onChange={choose} />;
  if (visible.length < 2) {
    return (
      <div className="space-y-2 text-xs text-muted">
        {ranges}
        <p>Moins de deux scans sur cette période : élargis-la sur la réglette.</p>
        {brush}
      </div>
    );
  }

  const first = visible[0];
  const last = visible[visible.length - 1];
  const prices = visible.map((p) => p.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const average = Math.round(prices.reduce((sum, price) => sum + price, 0) / prices.length);
  const change = Math.round(((last.price - first.price) * 1000) / first.price) / 10;
  const listed = visible.filter((p) => p.listed != null);
  const marks = [
    { v: thresholds?.buy ?? null, color: BUY_COLOR, label: "achat" },
    { v: thresholds?.sell ?? null, color: SELL_COLOR, label: "vente" },
  ].flatMap((m) => (m.v == null ? [] : [{ ...m, v: m.v, label: `${m.label} : ${formatMoney(m.v)}` }]));
  // Mes transactions de la période, celles dont le prix à l'unité est connu : hors de la période des scans,
  // elles restent dans le récapitulatif sous la courbe.
  const inside = (t: number) => t >= first.t && t <= last.t;
  const dots = trades.flatMap((trade) => {
    const t = new Date(trade.at).getTime();
    return trade.price != null && inside(t)
      ? [{ id: trade.id, t, v: trade.price, kind: trade.kind, label: tradeLabel(trade) }]
      : [];
  });
  const links = trips.flatMap((trip) => {
    const from = new Date(trip.bought_at).getTime();
    const to = new Date(trip.sold_at).getTime();
    return inside(from) && inside(to)
      ? [{ id: trip.sale, t1: from, v1: trip.buy_price, t2: to, v2: trip.sell_price, gain: trip.profit >= 0 }]
      : [];
  });
  // L'échelle s'étend jusqu'aux seuils et aux transactions : un repère hors du cadre ne dirait rien.
  const extra = [...marks.map((m) => m.v), ...dots.map((d) => d.v), ...links.map((l) => l.v1)];
  const low = Math.min(min, ...extra);
  const high = Math.max(max, ...extra);

  const plotWidth = Math.max(60, width - MARGIN.left - MARGIN.right);
  const span = Math.max(1, last.t - first.t);
  const x = (t: number) => MARGIN.left + ((t - first.t) / span) * plotWidth;
  const tickCount = Math.max(1, Math.min(6, Math.floor(plotWidth / 120)));
  const xTicks = Array.from({ length: tickCount + 1 }, (_, i) => first.t + (span * i) / tickCount);
  const tickFormat = span < 2 * DAY ? hourFormat : dayFormat;

  const hovered = hover != null ? visible[Math.min(hover, visible.length - 1)] : null;
  const nearest = (clientX: number, element: HTMLElement) => {
    const px = clientX - element.getBoundingClientRect().left;
    let best = 0;
    for (let i = 1; i < visible.length; i++) {
      if (Math.abs(x(visible[i].t) - px) < Math.abs(x(visible[best].t) - px)) best = i;
    }
    return best;
  };
  const step = (delta: number) =>
    setHover((current) => {
      const from = current ?? (delta > 0 ? -1 : visible.length);
      return Math.max(0, Math.min(visible.length - 1, from + delta));
    });

  const shared = { width, x, hoverT: hovered?.t ?? null };
  return (
    <div className="space-y-3 text-xs text-muted">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {ranges}
        <span>
          du {formatDateTime(first.at)} au {formatDateTime(last.at)} · {visible.length} scans
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Dernier prix" value={formatMoney(last.price)}>
          <span className={change === 0 ? undefined : change > 0 ? "text-success" : "text-danger"}>
            {formatChange(change)}
          </span>{" "}
          sur la période
        </Stat>
        <Stat label="Plus bas" value={formatMoney(min)} />
        <Stat label="Moyenne" value={formatMoney(average)} />
        <Stat label="Plus haut" value={formatMoney(max)} />
      </dl>

      <div
        ref={ref}
        className="relative touch-pan-y rounded-sm border border-border/60 bg-bg/60 py-2 focus-visible:outline-2 focus-visible:outline-gold"
        tabIndex={0}
        role="group"
        aria-label="Courbe de prix : flèches gauche et droite pour lire chaque scan"
        onPointerMove={(e) => setHover(nearest(e.clientX, e.currentTarget))}
        onPointerLeave={() => setHover(null)}
        onBlur={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
          e.preventDefault();
          step(e.key === "ArrowLeft" ? -1 : 1);
        }}
      >
        <PlotTitle color={PRICE_COLOR}>
          Prix le plus bas, à l'unité
          {dots.length > 0 && (
            <span className="ml-2">
              <span style={{ color: BUY_COLOR }}>▲</span> mes achats{" "}
              <span className="ml-1" style={{ color: SELL_COLOR }}>
                ▼
              </span>{" "}
              mes ventes
            </span>
          )}
        </PlotTitle>
        <Plot
          {...shared}
          height={220}
          color={PRICE_COLOR}
          series={visible.map((p) => ({ t: p.t, v: p.price }))}
          ticks={niceTicks(low, high, 4)}
          format={formatMoney}
          marks={marks}
          trades={dots}
          links={links}
          xTicks={xTicks.map((t) => ({ t, label: tickFormat.format(t) }))}
          label={`Prix de ${formatMoney(first.price)} à ${formatMoney(last.price)} sur ${visible.length} scans`}
        />
        {listed.length >= 2 && (
          <>
            <PlotTitle color={LISTED_COLOR}>Nombre d'enchères</PlotTitle>
            <Plot
              {...shared}
              height={96}
              color={LISTED_COLOR}
              series={listed.map((p) => ({ t: p.t, v: p.listed ?? 0 }))}
              ticks={niceTicks(0, Math.max(1, ...listed.map((p) => p.listed ?? 0)), 2)}
              format={(value) => String(value)}
              label={`Nombre d'enchères sur ${listed.length} scans`}
            />
          </>
        )}
        {hovered && (
          <div
            className="pointer-events-none absolute top-8 z-10 rounded-sm border border-border bg-surface-2 px-2.5 py-1.5 whitespace-nowrap shadow-lg"
            style={
              x(hovered.t) > width / 2 ? { right: width - x(hovered.t) + 12 } : { left: x(hovered.t) + 12 }
            }
          >
            <div>{formatDateTime(hovered.at)}</div>
            <div className="mt-1flex items-center gap-2">
              <span className="h-0.5 w-3 rounded-full" style={{ background: PRICE_COLOR }} />
              <span className="font-mono text-sm font-semibold text-text">{formatMoney(hovered.price)}</span>
            </div>
            {hovered.listed != null && (
              <div className="flex items-center gap-2">
                <span className="h-0.5 w-3 rounded-full" style={{ background: LISTED_COLOR }} />
                <span className="font-semibold text-text">{hovered.listed}</span> enchère
                {hovered.listed > 1 ? "s" : ""}
              </div>
            )}
            {hovered.by && <div className="mt-1">envoyé par {hovered.by}</div>}
          </div>
        )}
      </div>

      {brush}

      <details>
        <summary className="cursor-pointer hover:text-text">Voir les valeurs</summary>
        <div className="mt-2 max-h-56 overflow-y-auto rounded-sm border border-border/60">
          <table className="w-full text-left">
            <thead className="sticky top-0 bg-surface text-muted">
              <tr>
                <th className="px-2 py-1 font-normal">Scan</th>
                <th className="px-2 py-1 text-right font-normal">Prix</th>
                <th className="px-2 py-1 text-right font-normal">Enchères</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {[...visible].reverse().map((p) => (
                <tr key={p.at}>
                  <td className="px-2 py-1">{formatDateTime(p.at)}</td>
                  <td className="px-2 py-1 text-right font-mono text-text">{formatMoney(p.price)}</td>
                  <td className="px-2 py-1 text-right text-text">{p.listed ?? "?"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

const BRUSH_HEIGHT = 56;
const HANDLE = 10; // demi-largeur de prise d'une poignée, en pixels

/**
 * La réglette sous la courbe : tout l'historique en miniature, et la période affichée en surbrillance. On tire
 * une poignée pour changer un bord, le milieu pour déplacer la période, ailleurs pour en tracer une nouvelle ;
 * double-clic : tout l'historique. Au clavier, chaque poignée se règle avec les flèches.
 */
function Brush({
  width,
  points,
  period,
  onChange,
}: {
  width: number;
  points: Timed[];
  period: Period | null;
  onChange: (period: Period | null) => void;
}) {
  const drag = useRef<{ mode: "from" | "to" | "move" | "new"; px: number; from: number; to: number } | null>(
    null,
  );
  const start = points[0].t;
  const end = points[points.length - 1].t;
  const span = Math.max(1, end - start);
  const [from, to] = period ?? [start, end];
  const plotWidth = Math.max(60, width - MARGIN.left - MARGIN.right);
  const x = (t: number) => MARGIN.left + ((t - start) / span) * plotWidth;
  const time = (px: number) => start + ((px - MARGIN.left) / plotWidth) * span;
  const least = span / 50; // une période plus étroite ne se rattrape plus à la souris
  const clamp = (t: number) => Math.max(start, Math.min(end, t));

  const prices = points.map((p) => p.price);
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  const y = (v: number) => BRUSH_HEIGHT - 6 - ((v - low) / Math.max(1, high - low)) * (BRUSH_HEIGHT - 12);
  const line = points.map((p) => `${x(p.t).toFixed(1)},${y(p.price).toFixed(1)}`).join(" ");

  const moved = (clientX: number, element: Element) => {
    const state = drag.current;
    if (!state) return;
    const px = clientX - element.getBoundingClientRect().left;
    if (state.mode === "new" && Math.abs(px - state.px) < 4) return; // un simple clic ne change rien
    const t = clamp(time(px));
    if (state.mode === "from") onChange([Math.min(t, state.to - least), state.to]);
    else if (state.mode === "to") onChange([state.from, Math.max(t, state.from + least)]);
    else if (state.mode === "move") {
      const length = state.to - state.from;
      const shifted = Math.max(start, Math.min(end - length, state.from + time(px) - time(state.px)));
      onChange([shifted, shifted + length]);
    } else {
      const anchor = clamp(time(state.px));
      const a = Math.min(anchor, t);
      const b = Math.max(anchor, t);
      onChange(b - a >= least ? [a, b] : a + least <= end ? [a, a + least] : [end - least, end]);
    }
  };

  const nudge = (edge: "from" | "to") => (e: React.KeyboardEvent) => {
    const steps: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, PageDown: -5, PageUp: 5 };
    let t = edge === "from" ? from : to;
    if (e.key === "Home") t = start;
    else if (e.key === "End") t = end;
    else if (e.key in steps) t = clamp(t + steps[e.key] * least);
    else return;
    e.preventDefault();
    e.stopPropagation();
    onChange(edge === "from" ? [Math.min(t, to - least), to] : [from, Math.max(t, from + least)]);
  };
  const handle = (edge: "from" | "to") => {
    const t = edge === "from" ? from : to;
    return (
      <g
        tabIndex={0}
        role="slider"
        aria-label={edge === "from" ? "Début de la période" : "Fin de la période"}
        aria-valuemin={start}
        aria-valuemax={end}
        aria-valuenow={Math.round(t)}
        aria-valuetext={hourFormat.format(t)}
        onKeyDown={nudge(edge)}
        className="outline-none [&:focus-visible>rect]:fill-text"
      >
        <rect x={x(t) - 3} y={BRUSH_HEIGHT / 2 - 12} width="6" height="24" rx="2" fill={PRICE_COLOR} />
      </g>
    );
  };

  return (
    <div className="space-y-1">
      <svg
        width={width}
        height={BRUSH_HEIGHT}
        className="box-content block cursor-crosshair touch-pan-y rounded-sm border border-border/60 bg-bg/60 select-none"
        role="group"
        aria-label="Période affichée : tirer les poignées, ou le milieu pour la déplacer"
        onPointerDown={(e) => {
          const px = e.clientX - e.currentTarget.getBoundingClientRect().left;
          const mode =
            Math.abs(px - x(from)) <= HANDLE && (px <= x(from) || Math.abs(px - x(to)) > HANDLE)
              ? "from"
              : Math.abs(px - x(to)) <= HANDLE
                ? "to"
                : px > x(from) && px < x(to) && period
                  ? "move"
                  : "new";
          drag.current = { mode, px, from, to };
          e.currentTarget.setPointerCapture?.(e.pointerId);
        }}
        onPointerMove={(e) => moved(e.clientX, e.currentTarget)}
        onPointerUp={() => (drag.current = null)}
        onPointerCancel={() => (drag.current = null)}
        onDoubleClick={() => onChange(null)}
      >
        <polyline points={line} fill="none" stroke="var(--color-muted)" strokeWidth="1.5" opacity="0.7" />
        <rect
          x={x(from)}
          y="1"
          width={Math.max(1, x(to) - x(from))}
          height={BRUSH_HEIGHT - 2}
          fill={PRICE_COLOR}
          opacity="0.14"
          className={period ? "cursor-grab" : undefined}
        />
        <g className="cursor-ew-resize">
          {handle("from")}
          {handle("to")}
        </g>
      </svg>
      <div className="flex flex-wrap justify-between gap-2">
        <span>Tire les poignées ou le milieu pour régler la période ; double-clic : tout l'historique.</span>
        {period && (
          <button type="button" className="underline hover:text-text" onClick={() => onChange(null)}>
            Tout afficher
          </button>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, children }: { label: string; value: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-sm border border-border/60 bg-bg/40 px-2.5 py-1.5">
      <dt>{label}</dt>
      <dd className="font-mono text-sm text-text">{value}</dd>
      {children && <dd>{children}</dd>}
    </div>
  );
}

function PlotTitle({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 px-3 pt-1">
      <span className="h-0.5 w-3 rounded-full" style={{ background: color }} />
      {children}
    </div>
  );
}

/** Une série sur l'axe du temps partagé : grille et graduations discrètes, ligne de 2 px, repère au survol. */
function Plot({
  width,
  height,
  x,
  series,
  ticks,
  format,
  color,
  hoverT,
  xTicks,
  label,
  marks,
  trades,
  links,
}: {
  width: number;
  height: number;
  x: (t: number) => number;
  series: { t: number; v: number }[];
  ticks: number[];
  format: (value: number) => string;
  color: string;
  hoverT: number | null;
  xTicks?: { t: number; label: string }[];
  label: string;
  /** Lignes horizontales en pointillés, nommées au bord droit. */
  marks?: { v: number; color: string; label: string }[];
  /** Achats (triangle vert, pointe en haut) et ventes (triangle rouge, pointe en bas), décrits au survol. */
  trades?: { id: number; t: number; v: number; kind: "buy" | "sell"; label: string }[];
  /** Un trait par revente, de l'achat à la vente : vert si elle rapporte, rouge sinon. */
  links?: { id: number; t1: number; v1: number; t2: number; v2: number; gain: boolean }[];
}) {
  const top = MARGIN.top;
  const bottom = height - (xTicks ? MARGIN.bottom : 8);
  const low = ticks[0];
  const high = ticks[ticks.length - 1];
  const y = (v: number) => bottom - ((v - low) / Math.max(1, high - low)) * (bottom - top);
  const line = series.map((p) => `${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
  const start = x(series[0].t).toFixed(1);
  const end = x(series[series.length - 1].t).toFixed(1);
  const hovered = hoverT != null ? series.find((p) => p.t === hoverT) : undefined;
  return (
    <svg width={width} height={height} className="block" role="img" aria-label={label}>
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={MARGIN.left}
            x2={width - MARGIN.right}
            y1={y(tick)}
            y2={y(tick)}
            stroke="var(--color-border)"
            strokeWidth="1"
            opacity="0.6"
          />
          <text
            x={MARGIN.left - 8}
            y={y(tick)}
            textAnchor="end"
            dominantBaseline="middle"
            fontSize="11"
            fill="var(--color-muted)"
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {format(tick)}
          </text>
        </g>
      ))}
      {xTicks?.map((tick, i) => (
        <text
          key={tick.t}
          x={x(tick.t)}
          y={height - 6}
          textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}
          fontSize="11"
          fill="var(--color-muted)"
        >
          {tick.label}
        </text>
      ))}
      <polygon points={`${start},${bottom} ${line} ${end},${bottom}`} fill={color} opacity="0.1" />
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {marks?.map((mark) => (
        <g key={mark.label}>
          <line
            x1={MARGIN.left}
            x2={width - MARGIN.right}
            y1={y(mark.v)}
            y2={y(mark.v)}
            stroke={mark.color}
            strokeWidth="1.5"
            strokeDasharray="6 4"
          />
          <text
            x={width - MARGIN.right - 4}
            y={y(mark.v) - 5 < top + 8 ? y(mark.v) + 13 : y(mark.v) - 5}
            textAnchor="end"
            fontSize="11"
            fill={mark.color}
            stroke="var(--color-bg)"
            strokeWidth="3"
            paintOrder="stroke"
          >
            {mark.label}
          </text>
        </g>
      ))}
      {series.length <= MAX_DOTS &&
        series.map((p) => (
          <circle
            key={p.t}
            cx={x(p.t)}
            cy={y(p.v)}
            r="3"
            fill={color}
            stroke="var(--color-bg)"
            strokeWidth="1.5"
          />
        ))}
      {links?.map((link) => (
        <line
          key={link.id}
          x1={x(link.t1)}
          y1={y(link.v1)}
          x2={x(link.t2)}
          y2={y(link.v2)}
          stroke={link.gain ? BUY_COLOR : SELL_COLOR}
          strokeWidth="1.5"
          strokeDasharray="2 3"
          opacity="0.8"
        />
      ))}
      {trades?.map((trade) => {
        const cx = x(trade.t);
        const cy = y(trade.v);
        const tip = trade.kind === "buy" ? -6 : 6; // la pointe : en haut pour un achat, en bas pour une vente
        return (
          <path
            key={trade.id}
            d={`M${cx},${cy + tip} L${cx + 6},${cy - tip * 0.75} L${cx - 6},${cy - tip * 0.75} Z`}
            fill={trade.kind === "buy" ? BUY_COLOR : SELL_COLOR}
            stroke="var(--color-bg)"
            strokeWidth="1.5"
            strokeLinejoin="round"
          >
            <title>{trade.label}</title>
          </path>
        );
      })}
      {hoverT != null && (
        <line
          x1={x(hoverT)}
          x2={x(hoverT)}
          y1={top}
          y2={bottom}
          stroke="var(--color-muted)"
          strokeWidth="1"
        />
      )}
      {hovered && (
        <circle
          cx={x(hovered.t)}
          cy={y(hovered.v)}
          r="5"
          fill={color}
          stroke="var(--color-bg)"
          strokeWidth="2"
        />
      )}
    </svg>
  );
}
