import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, type AppState, type AuctionOutcome, type PullOutcome, type SyncOutcome } from "./api";

export function App() {
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState<string | null>(null);

  const refresh = () => api.getState().then(setState).catch((e) => setError(String(e)));

  useEffect(() => {
    void refresh();
    const unlisteners = [
      api.onSync((outcomes) => setState((s) => (s ? { ...s, last_sync: outcomes, last_sync_at: Math.floor(Date.now() / 1000) } : s))),
      api.onPull((outcome) => setState((s) => (s ? { ...s, last_pull: outcome, last_pull_at: Math.floor(Date.now() / 1000) } : s))),
      api.onAuctions((outcomes) => setState((s) => (s ? { ...s, last_auctions: outcomes } : s))),
      api.onUpdateAvailable((version) => setUpdating(version)),
      api.onUpdateStuck((version) => setState((s) => (s ? { ...s, update_stuck: version } : s))),
      api.onUpdateFailed((e) => {
        setUpdating(null);
        setError(`Mise à jour impossible : ${e}`);
      }),
    ];
    return () => {
      for (const u of unlisteners) void u.then((fn) => fn());
    };
  }, []);

  if (!state) return <div className="app"><div className="main">{error ?? "Chargement…"}</div></div>;

  const step = !state.game_dir ? "gamedir" : !state.paired ? "pair" : "status";

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Manuel Feralas</h1>
          <div className="muted">Compagnon · envoie tes données au site à chaque déconnexion</div>
        </div>
        {state.display_name && <div className="muted">Lié à {state.display_name}</div>}
      </header>
      <main className="main">
        {updating && <div className="card">Mise à jour vers la version {updating} en cours, le compagnon va redémarrer…</div>}
        {state.update_stuck && !updating && (
          <div className="card warn">
            La mise à jour {state.update_stuck} n'a pas pu s'installer : l'installateur n'a pas réussi à fermer le compagnon.
            Elle ne sera pas retentée toute seule avant demain. Télécharge l'installateur, quitte le compagnon (clic droit sur
            son icône près de l'horloge, « Quitter »), puis lance l'installateur.
            <div className="row">
              <button className="primary" onClick={() => api.openReleases().catch((e) => setError(String(e)))}>
                Télécharger la dernière version
              </button>
              <button onClick={() => api.checkUpdate().catch((e) => setError(String(e)))}>Réessayer maintenant</button>
            </div>
          </div>
        )}
        {state.game_dir_warning &&<div className="card warn">{state.game_dir_warning}</div>}
        {error && <div className="card ko">{error}</div>}
        {step === "gamedir" && <GameDirStep state={state} onDone={refresh} onError={setError} />}
        {step === "pair" && <PairStep state={state} onDone={refresh} onError={setError} />}
        {step === "status" && <StatusView state={state} onChange={refresh} onError={setError} />}
      </main>
      <footer className="footer">
        <span>Compagnon {state.version} · addon {state.addon_version}</span>
        <span>{state.game_dir ?? "dossier WoW non choisi"}</span>
      </footer>
    </div>
  );
}

function GameDirStep({ state, onDone, onError }: { state: AppState; onDone: () => void; onError: (e: string) => void }) {
  const choose = async (preset?: string) => {
    try {
      const path = preset ?? (await open({ directory: true, title: "Choisis le dossier World of Warcraft" }));
      if (typeof path === "string") {
        await api.setGameDir(path);
        onDone();
      }
    } catch (e) {
      onError(String(e));
    }
  };
  return (
    <section className="card">
      <h2>1. Où est installé le jeu ?</h2>
      <p className="muted">
        Le dossier <code>World of Warcraft</code> ou directement <code>_forever_</code>. Le compagnon y installera l'addon et
        surveillera les données qu'il écrit.
      </p>
      {state.candidates.length > 0 && (
        <ul className="plain">
          {state.candidates.map((c) => (
            <li key={c} className="row">
              <code>{c}</code>
              <button className="primary" onClick={() => choose(c)}>C'est celui-là</button>
            </li>
          ))}
        </ul>
      )}
      <div className="row">
        <button onClick={() => choose()}>{state.candidates.length ? "Un autre dossier…" : "Choisir le dossier…"}</button>
      </div>
    </section>
  );
}

function PairStep({ state, onDone, onError }: { state: AppState; onDone: () => void; onError: (e: string) => void }) {
  const [code, setCode] = useState("");
  const [name, setName] = useState(state.device_name);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await api.pair(code, name);
      onDone();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card">
      <h2>2. Lier au site</h2>
      <div className="steps">
        <div className="step"><span className="num">1</span><span>Sur le site, ouvre <b>Profil › Compagnon</b> puis « Lier un compagnon ».</span></div>
        <div className="step"><span className="num">2</span><span>Recopie le code à six caractères ci-dessous (valable dix minutes).</span></div>
      </div>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <input
          className="code"
          type="text"
          value={code}
          maxLength={6}
          autoFocus
          placeholder="ABC234"
          onChange={(e) => setCode(e.target.value.toUpperCase())}
        />
        <input type="text" value={name} maxLength={64} onChange={(e) => setName(e.target.value)} aria-label="Nom de cette machine" />
        <button className="primary" type="submit" disabled={busy || code.length < 6}>Lier</button>
      </form>
      <p className="muted">
        Site : <code>{state.site_url}</code>{" "}
        <button
          onClick={async () => {
            const url = window.prompt("Adresse du site", state.site_url);
            if (url) await api.setSettings({ site_url: url }).then(onDone).catch((e) => onError(String(e)));
          }}
        >
          changer
        </button>
      </p>
    </section>
  );
}

function OutcomeLine({ o }: { o: SyncOutcome }) {
  if (o.kind === "sent")
    return (
      <li>
        <span className="ok">{o.account}</span> : {o.summary}
        {o.characters.length > 0 && <span className="muted"> · {o.characters.join(", ")}</span>}
      </li>
    );
  if (o.kind === "failed") return <li><span className="ko">{o.account}</span> : {o.error}</li>;
  if (o.kind === "duplicate") return <li><span className="muted">{o.account} : déjà reçu par le site</span></li>;
  return <li><span className="muted">{o.account} : rien de nouveau</span></li>;
}

function AuctionLine({ o }: { o: AuctionOutcome }) {
  switch (o.kind) {
    case "sent":
      return (
        <li>
          <span className="ok">{o.house}</span> : scan de {new Date(o.scanned_at * 1000).toLocaleString()} envoyé ({o.items} objets)
        </li>
      );
    case "failed":
      return <li><span className="ko">Envoi impossible</span> : {o.error}</li>;
    case "duplicate":
      return <li><span className="muted">{o.house} : scan déjà reçu par le site</span></li>;
    case "unchanged":
      return <li><span className="muted">{o.house} : pas de nouveau scan</span></li>;
    case "not_allowed":
      return null;
  }
}

function pullText(o: PullOutcome): string {
  switch (o.kind) {
    case "completed":
      return `${o.characters} personnage${o.characters > 1 ? "s" : ""} complété${o.characters > 1 ? "s" : ""} depuis le site dans ${o.accounts.join(", ")}${
        o.created.length ? ` (fichier créé pour ${o.created.join(", ")})` : ""
      }.`;
    case "game_running":
      return "Le jeu tourne : l'addon sera complété depuis le site au prochain lancement, jeu fermé.";
    case "nothing":
      return `Rien à compléter : ${o.reason}.`;
    case "failed":
      return `Complétion impossible : ${o.error}`;
  }
}

function StatusView({ state, onChange, onError }: { state: AppState; onChange: () => void; onError: (e: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [updateMessage, setUpdateMessage] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      onChange();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const addonOk = state.installed_addon_version === state.addon_version;
  return (
    <>
      <section className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2>Synchronisation</h2>
          <span className="muted">{state.last_sync_at ? `dernier passage ${new Date(state.last_sync_at * 1000).toLocaleTimeString()}` : "en attente du premier fichier"}</span>
        </div>
        <p className="muted">
          Comptes WoW surveillés : {state.accounts.length ? state.accounts.join(", ") : "aucun fichier de l'addon pour l'instant (connecte un personnage puis déconnecte-toi)"}.
        </p>
        {state.last_sync && state.last_sync.length > 0 && (
          <ul className="plain">{state.last_sync.map((o, i) => <OutcomeLine key={i} o={o} />)}</ul>
        )}
        <div className="row">
          <button className="primary" disabled={busy} onClick={() => run(api.syncNow)}>Synchroniser maintenant</button>
          <button onClick={() => api.openSite("/profil")}>Ouvrir mon profil sur le site</button>
        </div>
        <p className="muted">
          Dans l'autre sens, au lancement et jeu fermé, le site complète l'addon de ce PC avec tout ce qu'il sait de tes
          personnages (autres PC, réinstallations) : rien ne repart de zéro.
          {state.last_pull && (
            <>
              {" "}
              <span className={state.last_pull.kind === "failed" ? "ko" : state.last_pull.kind === "completed" ? "ok" : undefined}>
                {pullText(state.last_pull)}
              </span>
              {state.last_pull_at && ` (${new Date(state.last_pull_at * 1000).toLocaleTimeString()})`}
            </>
          )}
        </p>
        <div className="row">
          <button disabled={busy} onClick={() => run(api.pullNow)}>Compléter depuis le site</button>
        </div>
      </section>

      {state.last_auctions && state.last_auctions.some((o) => o.kind !== "not_allowed") && (
        <section className="card">
          <h2>Hôtel des ventes</h2>
          <p className="muted">
            Chaque scan complet fait avec NaowhForever part au site à la déconnexion ou au /reload suivant.
          </p>
          <ul className="plain">{state.last_auctions.map((o, i) => <AuctionLine key={i} o={o} />)}</ul>
          <div className="row">
            <button onClick={() => api.openSite("/hv")}>Voir les prix sur le site</button>
          </div>
        </section>
      )}

      <section className="card">
        <h2>Addon</h2>
        <p className="muted">
          {state.installed_addon_version
            ? addonOk
              ? `Version ${state.installed_addon_version} installée dans le jeu, à jour.`
              : `Version ${state.installed_addon_version} dans le jeu, ${state.addon_version} disponible : sera mise à jour, puis /reload ou reconnexion.`
            : "Pas encore installé dans le jeu."}
        </p>
        <div className="row">
          <button disabled={busy} onClick={() => run(api.installAddon)}>{state.installed_addon_version ? "Réinstaller l'addon" : "Installer l'addon"}</button>
          <button disabled={busy} onClick={() => run(async () => setUpdateMessage(await api.checkUpdate()))}>Vérifier les mises à jour</button>
          {updateMessage && <span className="muted">{updateMessage}</span>}
        </div>
        <p className="muted">Le compagnon se met à jour tout seul : au lancement, toutes les 10 minutes et après chaque synchronisation. L'addon suit, puis /reload ou reconnexion.</p>
      </section>

      <section className="card">
        <h2>Réglages</h2>
        <label className="check">
          <input type="checkbox" checked={state.autostart} onChange={(e) => run(() => api.setSettings({ autostart: e.target.checked }))} />
          Démarrer avec l'ordinateur
        </label>
        <div className="row">
          <span className="muted">Machine : {state.device_name} · dossier : <code>{state.game_dir}</code></span>
        </div>
        <div className="row">
          <button
            className="danger"
            disabled={busy}
            onClick={() => {
              if (window.confirm("Dissocier ce compagnon du site ? Il faudra refaire l'appairage.")) void run(api.unpair);
            }}
          >
            Dissocier
          </button>
          <button onClick={() => run(() => api.setGameDir(""))}>Changer le dossier WoW</button>
        </div>
      </section>
    </>
  );
}
