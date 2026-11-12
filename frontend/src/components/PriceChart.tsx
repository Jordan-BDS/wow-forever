import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { formatChange, formatMoney, niceTicks, useAuctionHistory, type AuctionHistory } from "@/api/auctions";
import { Pill, Spinner } from "@/components/ui";
import { formatDateTime } from "@/lib/game";

type Point = AuctionHistory["points"][number];
type Range = "week" | "month" | "all";

const RANGES: { value: Range; label: string; days: number | null }[] = [
  { value: "week", label: "7 jours", days: 7 },
  { value: "month", label: "30 jours", days: 30 },
  { value: "all", label: "Tout", days: null },
];

const DAY = 86_400_000;
const MARGIN = { top: 10, right: 16, bottom: 24, left: 92 };
const PRICE_COLOR = "var(--color-gold)";
const LISTED_COLOR = "#8fb0ea";
const MAX_DOTS = 40; // au-delà, les points se touchent : la ligne seule

const dayFormat = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
const hourFormat = new Intl.DateTimeFormat("fr-FR", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (element.clientWidth) setWidth(element.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width) setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Historique d'un objet dans un hôtel des ventes : chargé à l'ouverture, puis tracé. */
export function ItemPriceHistory({ itemId, house }: { itemId: number; house: string }) {
  const history = useAuctionHistory(itemId, house);
  if (history.isError) return <p className="text-xs text-danger">Historique indisponible.</p>;
  if (!history.data) return <Spinner />;
  return <PriceHistory points={history.data.points} />;
}

/** Courbe du prix le plus bas et du nombre d'enchères d'un objet, scan après scan. */
export function PriceHistory({ points }: { points: Point[] }) {
  const [range, setRange] = useState<Range>("all");
  const [hover, setHover] = useState<number | null>(null);
  const [ref, width] = useWidth();

  const all = useMemo(() => points.map((p) => ({ ...p, t: new Date(p.at).getTime() })), [points]);
  const visible = useMemo(() => {
    const days = RANGES.find((r) => r.value === range)?.days;
    if (days == null || all.length === 0) return all;
    const from = all[all.length - 1].t - days * DAY; // compté depuis le dernier scan, pas depuis aujourd'hui
    return all.filter((p) => p.t >= from);
  }, [all, range]);

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
      {RANGES.map((r) => (
        <Pill
          key={r.value}
          active={range === r.value}
          onClick={() => {
            setRange(r.value);
            setHover(null);
          }}
        >
          {r.label}
        </Pill>
      ))}
    </div>
  );
  if (visible.length < 2) {
    return (
      <div className="space-y-2 text-xs text-muted">
        {ranges}
        <p>Moins de deux scans sur cette période.</p>
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
        <PlotTitle color={PRICE_COLOR}>Prix le plus bas, à l'unité</PlotTitle>
        <Plot
          {...shared}
          height={220}
          color={PRICE_COLOR}
          series={visible.map((p) => ({ t: p.t, v: p.price }))}
          ticks={niceTicks(min, max, 4)}
          format={formatMoney}
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
            <div className="mt-1 flex items-center gap-2">
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
          </div>
        )}
      </div>

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
