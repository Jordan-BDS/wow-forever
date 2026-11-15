import clsx from "clsx";
import { useState } from "react";
import { Navigate } from "react-router";
import { useAuctionReports, type AuctionReport } from "@/api/auctions";
import { useAddonErrors, type AddonError } from "@/api/sync";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Card, PageTitle, Pill, Spinner } from "@/components/ui";
import { formatDateTime } from "@/lib/game";

/**
 * Tests en jeu (GM seulement). À gauche, le test en cours : les envois de prix de l'hôtel des ventes, tels que
 * chaque compagnon les raconte (envoyé, rien de nouveau, illisible et pourquoi). À droite, ce que les addons
 * remontent d'eux-mêmes. La fiche de contrôle des collecteurs, toute cochée, n'est plus là (novembre 2026).
 */
export function TestsPage() {
  const me = useCurrentUser();
  if (me.site_role !== "gm") return <Navigate to="/roster" replace />;
  return (
    <>
      <PageTitle>Tests en jeu</PageTitle>
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          <AuctionReportsCard />
          <p className="text-xs text-muted">
            Pour provoquer un constat : un scan complet dans Auctionator (ou NaowhForever), puis /reload ou
            déconnexion. Le compagnon (0.7.12 au moins) lit le fichier dans la minute et dit ici ce qu'il en a
            fait. Le même constat répété ne fait qu'une ligne, avec son compte.
          </p>
        </div>
        <aside className="space-y-3">
          <AddonErrorsCard />
          <p className="text-xs text-muted">
            Une erreur Lua de l'addon commence par Interface/AddOns/WoWForeverGuilde/… Elles sont gardées dans
            le fichier de l'addon, visibles avec /mf erreurs, et remontent ici à l'envoi suivant.
          </p>
        </aside>
      </div>
    </>
  );
}

type Tone = "ok" | "quiet" | "bad";

const KINDS: Record<AuctionReport["kind"], { label: string; tone: Tone }> = {
  sent: { label: "Envoyé", tone: "ok" },
  unchanged: { label: "Rien de nouveau", tone: "quiet" },
  duplicate: { label: "Déjà reçu par le site", tone: "quiet" },
  no_file: { label: "Pas d'addon de scan", tone: "quiet" },
  no_scan: { label: "Pas de scan complet", tone: "bad" },
  unreadable: { label: "Fichier illisible", tone: "bad" },
  failed: { label: "Envoi refusé", tone: "bad" },
  not_allowed: { label: "Compte non autorisé", tone: "bad" },
};

type ReportFilter = "all" | "problems" | "sent" | "none";

const FILTERS: { value: ReportFilter; label: string; keep: (r: AuctionReport) => boolean }[] = [
  { value: "all", label: "Tout", keep: (r) => r.kind !== "no_file" },
  { value: "problems", label: "Ça coince", keep: (r) => KINDS[r.kind]?.tone === "bad" },
  { value: "sent", label: "Envoyés", keep: (r) => r.kind === "sent" },
  { value: "none", label: "Sans addon de scan", keep: (r) => r.kind === "no_file" },
];

const DAY_0 = Date.UTC(2020, 0, 1); // jour zéro d'Auctionator
const dayFormat = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", timeZone: "UTC" });

/** « jour 2507 (12 novembre) » : le jour compté par Auctionator, rendu lisible. */
function auctionatorDay(day: number): string {
  return `jour ${day} (${dayFormat.format(DAY_0 + day * 86_400_000)})`;
}

/** Les chiffres d'un constat, sur une ligne : objets, jour du scan, date envoyée au site, écriture du fichier. */
function reportFacts(r: AuctionReport): string[] {
  const facts: string[] = [];
  if (r.items != null) facts.push(`${r.items} objets`);
  if (r.day != null) facts.push(auctionatorDay(r.day));
  if (r.scanned_at) facts.push(`scan daté du ${formatDateTime(r.scanned_at)}`);
  if (r.file_at) facts.push(`fichier écrit le ${formatDateTime(r.file_at)}`);
  return facts;
}

/** Les constats des compagnons sur leurs fichiers de scan de l'hôtel des ventes. */
function AuctionReportsCard() {
  const reports = useAuctionReports();
  const [filter, setFilter] = useState<ReportFilter>("all");
  const [copied, setCopied] = useState(false);
  if (reports.isPending) return <Spinner />;
  const all = reports.data ?? [];
  const list = all.filter(FILTERS.find((f) => f.value === filter)?.keep ?? (() => true));
  const asText = list
    .map(
      (r) =>
        `${formatDateTime(r.at)} · ${r.user}${r.device ? ` · ${r.device}` : ""}${r.count > 1 ? ` · ×${r.count}` : ""} · compagnon ${
          r.companion || "?"
        }\n  ${r.source}${r.house ? ` ${r.house}` : ""} : ${KINDS[r.kind]?.label ?? r.kind}${r.detail ? ` — ${r.detail}` : ""}${
          reportFacts(r).length ? `\n  ${reportFacts(r).join(" · ")}` : ""
        }`,
    )
    .join("\n");
  const copyAll = async () => {
    try {
      await navigator.clipboard.writeText(asText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* presse-papiers refusé : le texte reste sélectionnable ci-dessous */
    }
  };
  const problems = all.filter(FILTERS[1].keep).length;
  return (
    <Card className={clsx("space-y-3", problems > 0 && "border-danger/40")}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl">Envois de l'hôtel des ventes</h2>
        <span className="text-xs text-muted">14 derniers jours · Auctionator et NaowhForever</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <Pill key={f.value} active={filter === f.value} onClick={() => setFilter(f.value)}>
            {f.label} ({all.filter(f.keep).length})
          </Pill>
        ))}
      </div>
      {reports.isError ? (
        <p className="text-sm text-danger">Impossible de charger les constats.</p>
      ) : list.length === 0 ? (
        <p className="text-sm text-muted">
          {all.length === 0
            ? "Aucun constat reçu. Ils arrivent des compagnons 0.7.12 et suivants, à leur premier passage."
            : "Aucun constat de ce genre."}
        </p>
      ) : (
        <>
          <ul className="space-y-2">
            {list.map((r) => (
              <ReportRow key={r.id} r={r} />
            ))}
          </ul>
          <button
            type="button"
            onClick={copyAll}
            className={clsx(
              "rounded-sm border px-3 py-1.5 text-sm transition-colors",
              copied
                ? "border-success text-success"
                : "border-border text-muted hover:border-gold hover:text-gold",
            )}
          >
            {copied ? "Tout copié" : `Tout copier (${list.length})`}
          </button>
        </>
      )}
    </Card>
  );
}

function ReportRow({ r }: { r: AuctionReport }) {
  const kind = KINDS[r.kind] ?? { label: r.kind, tone: "quiet" as Tone };
  const facts = reportFacts(r);
  return (
    <li
      className={clsx(
        "rounded-md border bg-bg/60 p-3 text-sm",
        kind.tone === "bad" ? "border-danger/40" : "border-border",
      )}
    >
      <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted">
        <span className="text-text">{formatDateTime(r.at)}</span>
        {r.count > 1 && <span className="text-gold-light">×{r.count}</span>}
        <span>{r.user}</span>
        {r.device && <span>· {r.device}</span>}
        <span>· compagnon {r.companion || "?"}</span>
        {r.count > 1 && <span>· depuis le {formatDateTime(r.first_at)}</span>}
      </div>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-2">
        <span
          className={clsx(
            "font-medium",
            kind.tone === "ok" ? "text-success" : kind.tone === "bad" ? "text-danger" : "text-text",
          )}
        >
          {kind.label}
        </span>
        <span className="text-gold-light">
          {r.source}
          {r.house && ` · ${r.house}`}
        </span>
      </div>
      {r.detail && <p className="mt-1 break-words">{r.detail}</p>}
      {facts.length > 0 && <p className="mt-1 text-xs text-muted">{facts.join(" · ")}</p>}
    </li>
  );
}

/** Erreurs des collecteurs remontées par les addons de toute la guilde, à copier d'un bloc. */
function AddonErrorsCard() {
  const errors = useAddonErrors(true);
  const [copied, setCopied] = useState(false);
  if (errors.isPending) return <Spinner />;
  const list = errors.data ?? [];
  const asText = list
    .map(
      (e) =>
        `${e.at ? formatDateTime(e.at) : "?"} · ${e.users.join(", ")}${e.count > 1 ? ` · ×${e.count}` : ""} · addon ${e.addons.join(", ")}${
          e.client ? ` · client ${e.client}` : ""
        }\n  ${e.where || "?"} : ${e.error}`,
    )
    .join("\n");
  const copyAll = async () => {
    try {
      await navigator.clipboard.writeText(asText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* presse-papiers refusé : le texte reste sélectionnable ci-dessous */
    }
  };
  return (
    <Card className={clsx("space-y-3", list.length > 0 && "border-danger/40")}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl">Erreurs remontées par les addons</h2>
        <span className="text-xs text-muted">
          7 derniers jours · toute la guilde · les identiques regroupées
        </span>
      </div>
      {errors.isError ? (
        <p className="text-sm text-danger">Impossible de charger les erreurs.</p>
      ) : list.length === 0 ? (
        <p className="text-sm text-muted">
          Aucune erreur reçue. Un collecteur qui plante est noté par l'addon et arrive ici au prochain envoi.
        </p>
      ) : (
        <>
          <ul className="space-y-2">
            {list.map((e, i) => (
              <ErrorRow key={`${e.user.id}-${e.at}-${i}`} e={e} />
            ))}
          </ul>
          <button
            type="button"
            onClick={copyAll}
            className={clsx(
              "rounded-sm border px-3 py-1.5 text-sm transition-colors",
              copied
                ? "border-success text-success"
                : "border-border text-muted hover:border-gold hover:text-gold",
            )}
          >
            {copied ? "Tout copié" : `Tout copier (${list.length})`}
          </button>
        </>
      )}
    </Card>
  );
}

function ErrorRow({ e }: { e: AddonError }) {
  return (
    <li className="rounded-md border border-border bg-bg/60 p-3 text-sm">
      <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted">
        <span className="text-text">{e.at ? formatDateTime(e.at) : "heure inconnue"}</span>
        {e.count > 1 && <span className="text-gold-light">×{e.count}</span>}
        <span>{e.users.join(", ")}</span>
        {e.count === 1 && e.device && <span>· {e.device}</span>}
        <span>· addon {e.addons.join(", ")}</span>
        {e.client && <span>· client {e.client}</span>}
        <span>· reçu {formatDateTime(e.received_at)}</span>
      </div>
      <div className="mt-1 max-h-48 overflow-y-auto font-mono text-[12.5px] break-words whitespace-pre-wrap">
        <span className="text-gold-light">{e.where || "?"}</span> : {e.error}
      </div>
    </li>
  );
}
