import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useState, type FormEvent } from "react";
import { formatMoney } from "@/api/auctions";
import {
  rewardParts,
  useBounties,
  useCancelBounty,
  usePayBounty,
  usePostBounty,
  type Bounty,
  type BountyItem,
  type LedgerLine,
} from "@/api/bounties";
import { api, errorMessage } from "@/api/client";
import { unwrap } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Button, Card, Field, Input, PageTitle, Spinner } from "@/components/ui";
import { formatDateTime } from "@/lib/game";
import { useDebounced } from "@/lib/useDebounced";
import { QUALITY_COLOR } from "@/lib/wowhead";

const STATUS: Record<Bounty["status"], string> = {
  open: "En cours",
  done: "Terminée",
  cancelled: "Annulée",
};

/** Primes posées à la main : un membre met tant par kill sur un joueur adverse, le site compte et tient les comptes. */
export function BountiesPage() {
  const report = useBounties();
  const me = useCurrentUser();

  if (report.isPending) return <Spinner />;
  if (report.isError || !report.data)
    return <p className="text-sm text-danger">Impossible de charger les primes.</p>;
  const { bounties, ledger } = report.data;

  return (
    <>
      <PageTitle>Primes</PageTitle>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
        <div className="min-w-0 space-y-4">
          <Ledger lines={ledger} me={me.id} />
          {bounties.length === 0 ? (
            <Card className="text-sm text-muted">Aucune prime pour l'instant. Pose la première.</Card>
          ) : (
            bounties.map((bounty) => <BountyCard key={bounty.id} bounty={bounty} />)
          )}
        </div>
        <NewBountyForm />
      </div>
    </>
  );
}

/** Qui doit quoi à qui, toutes primes confondues. Les lignes qui me concernent sont en tête. */
function Ledger({ lines, me }: { lines: LedgerLine[]; me: number }) {
  if (lines.length === 0) {
    return <Card className="text-sm text-muted">Personne ne doit rien à personne.</Card>;
  }
  const mine = (line: LedgerLine) => line.from.id === me || line.to.id === me;
  const sorted = [...lines].sort((a, b) => Number(mine(b)) - Number(mine(a)));
  return (
    <Card>
      <h2 className="mb-2 font-display text-lg">Qui doit quoi à qui</h2>
      <ul className="divide-y divide-border/60 text-sm">
        {sorted.map((line) => (
          <li
            key={`${line.from.id}-${line.to.id}`}
            className={clsx("flex flex-wrap items-baseline gap-x-2 py-1.5", mine(line) && "text-gold-light")}
          >
            <span className="font-medium">{line.from.display_name}</span>
            <span className="text-muted">doit à</span>
            <span className="font-medium">{line.to.display_name}</span>
            <span className="ml-auto text-right font-mono">
              {[
                line.amount > 0 ? formatMoney(line.amount) : "",
                ...line.items.map((item) => `${item.count} × ${item.name}`),
              ]
                .filter(Boolean)
                .join(" + ")}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted">
        Le paiement se fait en jeu : le commanditaire le déclare ensuite sur sa prime.
      </p>
    </Card>
  );
}

function BountyCard({ bounty }: { bounty: Bounty }) {
  const cancel = useCancelBounty();
  const pay = usePayBounty();
  const reward = rewardParts(bounty.amount, bounty.item_count, bounty.item?.name).join(" + ");
  const failed = cancel.error ?? pay.error;

  return (
    <Card className={clsx("space-y-3", bounty.status !== "open" && "opacity-80")}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="font-display text-lg">{bounty.target}</h2>
        <span className="font-mono text-sm text-gold-light">{reward} par kill</span>
        <span
          className={clsx(
            "rounded-full border px-2 py-0.5 text-xs",
            bounty.status === "open" ? "border-gold text-gold-light" : "border-border text-muted",
          )}
        >
          {STATUS[bounty.status]} · {bounty.kills.length} / {bounty.max_kills} kill
          {bounty.max_kills > 1 ? "s" : ""}
        </span>
        {bounty.can_cancel && bounty.status === "open" && (
          <Button
            variant="ghost"
            className="ml-auto"
            disabled={cancel.isPending}
            onClick={() => {
              if (window.confirm("Annuler cette prime ? Les kills déjà faits restent dus."))
                cancel.mutate(bounty.id);
            }}
          >
            Annuler
          </Button>
        )}
      </div>
      <p className="text-xs text-muted">
        Posée par {bounty.poster.display_name} le {formatDateTime(bounty.created_at)}
        {bounty.cancelled_at ? ` · annulée le ${formatDateTime(bounty.cancelled_at)}` : ""}
        {bounty.note ? ` · « ${bounty.note} »` : ""}
      </p>

      {bounty.dues.length > 0 && (
        <ul className="divide-y divide-border/60 text-sm">
          {bounty.dues.map((due) => {
            const owed = rewardParts(due.owed, due.items_owed, bounty.item?.name);
            const settled = owed.length === 0;
            return (
              <li key={due.hunter.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5">
                <span className="font-medium">{due.hunter.display_name}</span>
                <span className="text-xs text-muted">
                  {due.kills} kill{due.kills > 1 ? "s" : ""}
                </span>
                <span className={clsx("ml-auto font-mono", settled ? "text-success" : "")}>
                  {settled
                    ? "payé"
                    : `reste ${due.owed > 0 ? formatMoney(due.owed) : ""}${
                        due.owed > 0 && due.items_owed > 0 ? " + " : ""
                      }${due.items_owed > 0 ? `${due.items_owed} × ${bounty.item?.name ?? "objet"}` : ""}`}
                </span>
                {!settled && bounty.can_pay && (
                  <Button
                    variant="ghost"
                    disabled={pay.isPending}
                    onClick={() => pay.mutate({ id: bounty.id, hunterId: due.hunter.id })}
                  >
                    J'ai payé
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {bounty.kills.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted">Kills comptés</summary>
          <ul className="mt-1 space-y-0.5 text-xs text-muted">
            {bounty.kills.map((kill) => (
              <li key={kill.at}>
                {formatDateTime(kill.at)}
                {kill.zone ? ` · ${kill.zone}` : ""} · {kill.hunters.map((h) => h.character.name).join(", ")}
              </li>
            ))}
          </ul>
        </details>
      )}
      {failed != null && <p className="text-sm text-danger">{errorMessage(failed)}</p>}
    </Card>
  );
}

function NewBountyForm() {
  const post = usePostBounty();
  const [target, setTarget] = useState("");
  const [gold, setGold] = useState("");
  const [maxKills, setMaxKills] = useState("1");
  const [note, setNote] = useState("");
  const [item, setItem] = useState<BountyItem | null>(null);
  const [itemCount, setItemCount] = useState("1");

  const whole = (text: string) => (/^\d+$/.test(text.trim()) ? Number(text.trim()) : NaN);
  const goldValue = gold.trim() === "" ? 0 : whole(gold);
  const kills = whole(maxKills);
  const count = whole(itemCount);
  const ready =
    target.trim().length >= 2 &&
    Number.isFinite(goldValue) &&
    kills >= 1 &&
    (goldValue > 0 || item != null) &&
    (item == null || count >= 1);
  const most = rewardParts(goldValue * kills * 10000, item ? count * kills : 0, item?.name).join(" + ");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    post.mutate(
      {
        target: target.trim(),
        gold: goldValue,
        max_kills: kills,
        note: note.trim() || undefined,
        ...(item ? { item_id: item.id, item_count: count } : {}),
      },
      {
        onSuccess: () => {
          setTarget("");
          setGold("");
          setMaxKills("1");
          setNote("");
          setItem(null);
          setItemCount("1");
        },
      },
    );
  };

  return (
    <Card>
      <h2 className="mb-3 font-display text-lg">Poser une prime</h2>
      <form className="space-y-3" onSubmit={submit}>
        <Field label="Joueur adverse (nom exact en jeu)">
          <Input value={target} maxLength={64} onChange={(e) => setTarget(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Or par kill (po)">
            <Input
              value={gold}
              inputMode="numeric"
              placeholder="0"
              onChange={(e) => setGold(e.target.value)}
            />
          </Field>
          <Field label="Kills payés au plus">
            <Input value={maxKills} inputMode="numeric" onChange={(e) => setMaxKills(e.target.value)} />
          </Field>
        </div>
        <ItemChoice item={item} count={itemCount} onItem={setItem} onCount={setItemCount} />
        <Field label="Un mot (facultatif)">
          <Input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {ready && most && <p className="text-xs text-muted">Tu t'engages pour {most} au plus.</p>}
        {post.error != null && <p className="text-sm text-danger">{errorMessage(post.error)}</p>}
        <Button type="submit" disabled={!ready || post.isPending}>
          Poser la prime
        </Button>
      </form>
    </Card>
  );
}

/** Objets offerts par kill, en plus ou à la place de l'or : recherche dans l'index du site. */
function ItemChoice({
  item,
  count,
  onItem,
  onCount,
}: {
  item: BountyItem | null;
  count: string;
  onItem: (item: BountyItem | null) => void;
  onCount: (count: string) => void;
}) {
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim());
  const found = useQuery({
    queryKey: ["items", q, "bounty"],
    enabled: item == null && q.length >= 2,
    queryFn: () => unwrap(api.GET("/api/items/", { params: { query: { q } } })),
  });

  if (item) {
    return (
      <div className="space-y-1 text-sm">
        <span className="text-muted">Objets par kill</span>
        <div className="flex items-center gap-2">
          <Input
            value={count}
            inputMode="numeric"
            className="w-16"
            aria-label="Nombre d'objets par kill"
            onChange={(e) => onCount(e.target.value)}
          />
          <span>×</span>
          <img src={item.icon_url} alt="" className="size-6 rounded border border-border" />
          <span className="min-w-0 flex-1 truncate" style={{ color: QUALITY_COLOR[item.quality] }}>
            {item.name}
          </span>
          <Button variant="ghost" aria-label="Retirer l'objet" onClick={() => onItem(null)}>
            ✕
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <Field label="Objet offert par kill (facultatif)">
        <Input value={query} placeholder="Rechercher un objet…" onChange={(e) => setQuery(e.target.value)} />
      </Field>
      {q.length >= 2 && found.data && (
        <ul className="max-h-48 overflow-y-auto rounded-sm border border-border text-sm">
          {found.data.length === 0 && <li className="px-2 py-1.5 text-muted">Aucun objet trouvé.</li>}
          {found.data.slice(0, 20).map((candidate) => (
            <li key={candidate.id}>
              <button
                type="button"
                className="flex w-full items-center gap-2 px-2 py-1.5 text-left hover:bg-surface-2"
                onClick={() => {
                  onItem({
                    id: candidate.id,
                    name: candidate.name,
                    quality: candidate.quality ?? 1,
                    icon_url: candidate.icon_url,
                  });
                  setQuery("");
                }}
              >
                <img src={candidate.icon_url} alt="" className="size-6 rounded border border-border" />
                <span className="truncate" style={{ color: QUALITY_COLOR[candidate.quality ?? 1] }}>
                  {candidate.name}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
