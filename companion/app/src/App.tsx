import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, type AppState, type SyncOutcome } from "./api";

export function App() {
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState<string | null>(null);

  const refresh = () => api.getState().then(setState).catch((e) => setError(String(e)));

  useEffect(() => {
    void refresh();
    const unlisteners = [
      api.onSync((outcomes) => setState((s) => (s ? { ...s, last_sync: outcomes, last_sync_at: Math.floor(Date.now() / 1000) } : s))),
      api.onUpdateAvailable((version) => setUpdating(version)),
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
          <h1>WoW Forever Guilde</h1>
          <div className="muted">Compagnon · envoie tes données au site à chaque déconnexion</div>
        </div>
        {state.display_name && <div className="muted">Lié à {state.display_name}</div>}
      </header>
      <main className="main">
        {updating && <div className="card">Mise à jour vers la version {updating} en cours, le compagnon va redémarrer…</div>}
        {state.game_dir_warning && <div className="card warn">{state.game_dir_warning}</div>}
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

function StatusView({ state, onChange, onError }: { state: AppState; onChange: () => void; onError: (e: string) => void }) {
  const [busy, setBusy] = useState(false);
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
      </section>

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
        </div>
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
