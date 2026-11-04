import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorMessage, type CharacterSnapshot, type ImportBatch } from "@/api/client";
import {
  KEYS,
  useCharacters,
  useInvalidate,
  useSyncDevices,
  useSyncPending,
  useSyncRelease,
} from "@/api/hooks";
import clsx from "clsx";
import { Link } from "react-router";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Button, Card, Field, Spinner, Textarea } from "@/components/ui";
import { formatAgo, formatDateTime } from "@/lib/game";

const STATUS_LABEL: Record<CharacterSnapshot["status"], string> = {
  applied: "mis à jour",
  created: "créé",
  pending: "à rattacher",
  ignored: "ignoré",
  stale: "plus ancien que le dernier import",
  refused: "refusé",
};

const STATUS_CLASS: Record<CharacterSnapshot["status"], string> = {
  applied: "text-success",
  created: "text-success",
  pending: "text-[#e2b86a]",
  ignored: "text-muted",
  stale: "text-muted",
  refused: "text-danger",
};

function summarize(batch: ImportBatch): string {
  const s = batch.summary as Record<string, number>;
  const parts = [
    s.applied ? `${s.applied} mis à jour` : null,
    s.created ? `${s.created} créé${s.created > 1 ? "s" : ""}` : null,
    s.pending ? `${s.pending} à rattacher` : null,
    s.ignored ? `${s.ignored} ignoré${s.ignored > 1 ? "s" : ""}` : null,
    s.stale ? `${s.stale} déjà à jour` : null,
    s.refused ? `${s.refused} refusé${s.refused > 1 ? "s" : ""}` : null,
    s.new_recipes
      ? `${s.new_recipes} nouvelle${s.new_recipes > 1 ? "s" : ""} recette${s.new_recipes > 1 ? "s" : ""}`
      : null,
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : "rien de nouveau";
}

/** Collage du code d'export de l'addon (chemin sans compagnon). `plain` : sans carte, pour s'emboîter ailleurs. */
export function GameImportCard({ plain = false }: { plain?: boolean }) {
  const invalidate = useInvalidate();
  const [code, setCode] = useState("");
  const [result, setResult] = useState<ImportBatch | null>(null);
  const [error, setError] = useState<string | null>(null);

  const importCode = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST("/api/sync/import/", { body: { code } });
      if (response.status === 409) throw new Error("Ce code a déjà été importé : rien de nouveau.");
      if (error || !data) throw error ?? new Error();
      return data;
    },
    onSuccess: async (batch) => {
      setResult(batch);
      setError(null);
      setCode("");
      await invalidate(KEYS.characters, KEYS.syncPending, KEYS.syncImports);
    },
    onError: (e) => {
      setResult(null);
      setError(e instanceof Error && e.message ? e.message : errorMessage(e));
    },
  });

  const Wrapper = plain ? "div" : Card;
  return (
    <Wrapper className="space-y-3">
      {!plain && (
        <div>
          <h2 className="font-display text-lg">Importer depuis le jeu</h2>
          <p className="text-xs text-muted">
            Dans le jeu, ouvre la fenêtre de l'addon, « Exporter le code », Ctrl+C, puis colle ici. Avec le
            compagnon installé, c'est automatique à chaque déconnexion.
          </p>
        </div>
      )}
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (code.trim()) importCode.mutate();
        }}
      >
        <Field label="Code d'export">
          <Textarea
            value={code}
            rows={4}
            spellCheck={false}
            placeholder="WFG1:…"
            className="font-mono text-xs"
            onChange={(e) => setCode(e.target.value)}
          />
        </Field>
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={importCode.isPending || !code.trim()}>
            Importer
          </Button>
          {error && <span className="text-sm text-danger">{error}</span>}
        </div>
      </form>
      {result && <ImportResult batch={result} />}
    </Wrapper>
  );
}

function ImportResult({ batch }: { batch: ImportBatch }) {
  return (
    <div className="rounded-md border border-border bg-bg/60 p-3 text-sm">
      <p className="font-medium">Import terminé : {summarize(batch)}.</p>
      <ul className="mt-2 space-y-1">
        {batch.snapshots.map((s) => (
          <li key={s.id} className="flex flex-wrap items-baseline gap-x-2">
            <span>
              {s.full_name || s.name || "?"}
              {s.level ? <span className="text-muted"> · {s.level}</span> : null}
            </span>
            <span className={STATUS_CLASS[s.status]}>{STATUS_LABEL[s.status]}</span>
            {s.note && s.note !== "low_level" && <span className="text-xs text-muted">{s.note}</span>}
            {s.note === "low_level" && (
              <span className="text-xs text-muted">niveau &lt; 10, voir « À rattacher »</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Personnages du jeu encore à rattacher (fusion proposée) ou ignorés faute de niveau. */
export function PendingCharactersCard() {
  const pending = useSyncPending();
  const characters = useCharacters();
  const invalidate = useInvalidate();
  const [error, setError] = useState<string | null>(null);
  const [choice, setChoice] = useState<Record<number, number | "">>({});

  const resolve = useMutation({
    mutationFn: async (vars: {
      id: number;
      action: "merge" | "create" | "ignore";
      character_id?: number | null;
    }) => {
      const { error } = await api.POST("/api/sync/pending/{id}/resolve/", {
        params: { path: { id: vars.id } },
        body: { action: vars.action, character_id: vars.character_id ?? null },
      });
      if (error) throw error;
    },
    onSuccess: async () => {
      setError(null);
      await invalidate(KEYS.characters, KEYS.syncPending, KEYS.syncImports);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  if (pending.isPending) return <Spinner />;
  const items = pending.data ?? [];
  if (items.length === 0) return null;
  const mine = (characters.data ?? []).filter((c) => !c.guid);

  return (
    <Card className="space-y-3">
      <div>
        <h2 className="font-display text-lg">Personnages à rattacher</h2>
        <p className="text-xs text-muted">
          Reçus depuis le jeu, mais le site ne sait pas encore quoi en faire. Rien n'est fusionné sans ton
          accord.
        </p>
      </div>
      <ul className="space-y-3">
        {items.map((s) => (
          <li key={s.id} className="rounded-md border border-border bg-bg/60 p-3 text-sm">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-medium">{s.full_name || s.name}</span>
              {s.level ? <span className="text-muted">niveau {s.level}</span> : null}
              {s.low_level ? (
                <span className="text-xs text-muted">ignoré par défaut sous le niveau 10</span>
              ) : (
                <span className="text-xs text-[#e2b86a]">{s.note}</span>
              )}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {!s.low_level && mine.length > 0 && (
                <>
                  <select
                    className="rounded-sm border border-border bg-bg px-2 py-1 text-sm"
                    value={choice[s.id] ?? s.candidate?.id ?? ""}
                    onChange={(e) =>
                      setChoice((c) => ({ ...c, [s.id]: e.target.value ? Number(e.target.value) : "" }))
                    }
                  >
                    <option value="">Fusionner avec…</option>
                    {mine.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.level})
                      </option>
                    ))}
                  </select>
                  <Button
                    variant="ghost"
                    disabled={resolve.isPending || !(choice[s.id] ?? s.candidate?.id)}
                    onClick={() =>
                      resolve.mutate({
                        id: s.id,
                        action: "merge",
                        character_id: Number(choice[s.id] ?? s.candidate?.id),
                      })
                    }
                  >
                    Fusionner
                  </Button>
                </>
              )}
              <Button
                variant="ghost"
                disabled={resolve.isPending}
                onClick={() => resolve.mutate({ id: s.id, action: "create" })}
              >
                {s.low_level ? "Inclure quand même" : "Créer un nouveau personnage"}
              </Button>
              <Button
                variant="ghost"
                disabled={resolve.isPending}
                onClick={() => resolve.mutate({ id: s.id, action: "ignore" })}
              >
                Ignorer
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {error && <p className="text-sm text-danger">{error}</p>}
    </Card>
  );
}

const ROMAN = ["I", "II", "III", "IV"];

/**
 * Bande « Depuis le jeu » du profil : les quatre étapes qui amènent un personnage sur le site, reliées par un fil
 * d'or qui se remplit au fur et à mesure. Téléchargement, appairage, consigne en jeu, personnages reçus.
 */
export function SyncJourney() {
  const release = useSyncRelease();
  const devices = useSyncDevices();
  const characters = useCharacters();
  const me = useCurrentUser();
  const invalidate = useInvalidate();
  const [pairing, setPairing] = useState<{ code: string; expires_at: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const generate = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/sync/pairing-code/");
      if (error || !data) throw error ?? new Error();
      return data;
    },
    onSuccess: (data) => {
      setPairing(data);
      setError(null);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const revoke = useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.POST("/api/sync/devices/{id}/revoke/", { params: { path: { id } } });
      if (error) throw error;
    },
    onSuccess: () => invalidate(KEYS.syncDevices),
    onError: (e) => setError(errorMessage(e)),
  });

  const allDevices = devices.data ?? [];
  const active = allDevices.filter((d) => !d.revoked_at);
  const synced = (characters.data ?? [])
    .filter((c) => c.owner.id === me.id && c.guid)
    .sort((a, b) => (b.last_synced_at ?? "").localeCompare(a.last_synced_at ?? ""));
  const lastSync = synced[0]?.last_synced_at ?? null;
  const done = [allDevices.length > 0, active.length > 0, synced.length > 0, synced.length > 0];

  return (
    <section className="rounded-md border border-gold/40 bg-surface-2/70 bg-gradient-to-b from-surface-2/80 to-surface/90 p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="font-display text-xl">Depuis le jeu</h2>
        <p className="text-sm text-muted">
          {synced.length === 0
            ? "Ton personnage n'a pas encore été reçu. Quatre étapes, la première fois seulement."
            : lastSync
              ? `Dernier envoi ${formatAgo(lastSync)}.`
              : "Personnages reçus."}
        </p>
      </div>

      <ol className="grid gap-x-4 gap-y-6 md:grid-cols-4">
        <Step n={0} done={done} title="Installe le compagnon">
          {release.data ? (
            <div className="flex flex-wrap items-center gap-2">
              {release.data.assets.windows && (
                <a href={release.data.assets.windows} className="inline-flex">
                  <Button type="button">Windows</Button>
                </a>
              )}
              {release.data.assets.macos && (
                <a href={release.data.assets.macos} className="inline-flex">
                  <Button type="button" variant="ghost">
                    macOS
                  </Button>
                </a>
              )}
              {release.data.assets.addon && (
                <a href={release.data.assets.addon} className="text-xs">
                  Addon seul (zip)
                </a>
              )}
              <span className="text-xs text-muted">version {release.data.version}</span>
            </div>
          ) : (
            <p className="text-sm text-muted">Le compagnon n'est pas encore publié.</p>
          )}
          <p className="text-xs text-muted">
            Il installe l'addon dans ton dossier WoW et envoie tes données tout seul. Sans lui : le zip de
            l'addon dans Interface/AddOns, et le code à coller plus bas.
          </p>
        </Step>

        <Step n={1} done={done} title="Lie-le à ton compte">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" disabled={generate.isPending} onClick={() => generate.mutate()}>
              {pairing ? "Nouveau code" : active.length > 0 ? "Lier un autre PC" : "Obtenir un code"}
            </Button>
          </div>
          {pairing && (
            <p className="text-sm">
              À saisir dans le compagnon :{" "}
              <code className="rounded bg-bg px-2 py-1 font-mono text-lg tracking-widest text-gold">
                {pairing.code}
              </code>
              <span className="block text-xs text-muted">
                valable jusqu'à {formatDateTime(pairing.expires_at)}
              </span>
            </p>
          )}
          {active.length > 0 && (
            <ul className="space-y-1 text-sm">
              {active.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-x-2">
                  <span>{d.name}</span>
                  <span className="text-xs text-muted">
                    {d.last_seen_at ? `vu ${formatAgo(d.last_seen_at)}` : "jamais connecté"}
                  </span>
                  <button
                    type="button"
                    className="text-xs text-muted underline-offset-2 hover:text-danger hover:underline"
                    disabled={revoke.isPending}
                    onClick={() => {
                      if (window.confirm(`Révoquer « ${d.name} » ? Il devra être lié de nouveau.`))
                        revoke.mutate(d.id);
                    }}
                  >
                    révoquer
                  </button>
                </li>
              ))}
            </ul>
          )}
          {error && <p className="text-xs text-danger">{error}</p>}
        </Step>

        <Step n={2} done={done} title="En jeu, envoie ton personnage">
          <p className="text-sm">
            Tape <code className="rounded bg-bg px-1.5 py-0.5 font-mono text-xs text-gold">/mf</code> et
            laisse « Envoyer ce personnage » coché. Les données partent à chaque déconnexion ou /reload.
          </p>
          <p className="text-xs text-muted">
            Niveau, métiers, recettes, talents, équipement : tout vient du jeu, rien à saisir ici.
          </p>
        </Step>

        <Step n={3} done={done} title="Tes personnages">
          {synced.length === 0 ? (
            <p className="text-sm text-muted">Ils apparaîtront ici au premier envoi.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {synced.map((c) => (
                <li key={c.id} className="flex flex-wrap items-baseline gap-x-2">
                  <Link to={`/personnages/${c.id}`}>{c.name}</Link>
                  <span className="text-xs text-muted">
                    niveau {c.level}
                    {c.last_synced_at ? ` · ${formatAgo(c.last_synced_at)}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Step>
      </ol>

      <details className="mt-5 border-t border-border/70 pt-3 text-sm">
        <summary className="cursor-pointer text-muted hover:text-text">
          Sans compagnon : coller un code d'export
        </summary>
        <p className="mt-2 mb-3 text-xs text-muted">
          Dans le jeu, /mf puis « Exporter le code », Ctrl+C, et colle ici.
        </p>
        <GameImportCard plain />
      </details>
    </section>
  );
}

function Step({
  n,
  done,
  title,
  children,
}: {
  n: number;
  done: boolean[];
  title: string;
  children: React.ReactNode;
}) {
  const isDone = done[n];
  const threadDone = n > 0 && done[n - 1];
  return (
    <li
      className={clsx(
        "relative space-y-2 border-l border-border pl-5 md:border-0 md:pl-0",
        // Fil du bord droit du médaillon précédent au bord gauche de celui-ci, sans passer sous les titres.
        n > 0 &&
          "md:before:absolute md:before:top-[17px] md:before:right-[calc(100%+4px)] md:before:left-[calc(-100%-1rem+2.25rem+4px)] md:before:h-px",
        n > 0 && (threadDone ? "md:before:bg-gold" : "md:before:bg-border"),
      )}
    >
      <span
        className={clsx(
          "relative z-10 flex size-9 shrink-0 items-center justify-center rounded-full border-2 font-display text-sm",
          isDone ? "border-gold bg-gold text-bg" : "border-gold/70 bg-surface text-gold",
        )}
        aria-label={isDone ? "fait" : "à faire"}
      >
        {ROMAN[n]}
      </span>
      <h3 className="font-display text-base leading-tight">{title}</h3>
      <div className="space-y-2">{children}</div>
    </li>
  );
}
