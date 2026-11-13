// Pont vers le noyau Rust (commandes Tauri) et événements de fond.
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export type AppState = {
  version: string;
  addon_version: string;
  site_url: string;
  game_dir: string | null;
  device_name: string;
  paired: boolean;
  display_name: string | null;
  autostart: boolean;
  accounts: string[];
  installed_addon_version: string | null;
  last_sync: SyncOutcome[] | null;
  last_sync_at: number | null; // secondes epoch
  last_pull: PullOutcome | null;
  last_pull_at: number | null;
  last_auctions: AuctionOutcome[] | null;
  candidates: string[];
  game_dir_warning: string | null;
  update_stuck: string | null; // version dont l'installation n'a pas abouti
};

export type SyncOutcome =
  | { kind: "unchanged"; account: string }
  | { kind: "sent"; account: string; summary: string; characters: string[] }
  | { kind: "duplicate"; account: string }
  | { kind: "failed"; account: string; error: string };

// Sens site → addon : le site complète le fichier de l'addon de ce PC, jeu fermé.
export type PullOutcome =
  | { kind: "game_running" }
  | { kind: "nothing"; reason: string }
  | { kind: "completed"; accounts: string[]; characters: number; created: string[] }
  | { kind: "failed"; error: string };

// Scans de l'hôtel des ventes lus dans le fichier de l'addon NaowhForever, envoyés par le compagnon du GM.
export type AuctionOutcome =
  | { kind: "not_allowed" }
  | { kind: "unchanged"; house: string }
  | { kind: "sent"; house: string; scanned_at: number; items: number }
  | { kind: "duplicate"; house: string }
  | { kind: "failed"; error: string };

export const api = {
  getState: () => invoke<AppState>("get_state"),
  setGameDir: (path: string) => invoke<AppState>("set_game_dir", { path }),
  pair: (code: string, deviceName: string) => invoke<AppState>("pair", { code, deviceName }),
  unpair: () => invoke<AppState>("unpair"),
  syncNow: () => invoke<SyncOutcome[]>("sync_now"),
  pullNow: () => invoke<PullOutcome | null>("pull_now"),
  installAddon: () => invoke<string>("install_addon"),
  checkUpdate: () => invoke<string>("check_update"),
  setSettings: (settings: { autostart?: boolean; site_url?: string }) =>
    invoke<AppState>("set_settings", { settings }),
  openSite: (path: string) => invoke<void>("open_site", { path }),
  openReleases: () => invoke<void>("open_releases"),
  onUpdateStuck: (handler: (version: string) => void): Promise<UnlistenFn> =>
    listen<string>("update-stuck", (e) => handler(e.payload)),
  onSync: (handler: (outcomes: SyncOutcome[]) => void): Promise<UnlistenFn> =>
    listen<SyncOutcome[]>("sync-result", (e) => handler(e.payload)),
  onPull: (handler: (outcome: PullOutcome) => void): Promise<UnlistenFn> =>
    listen<PullOutcome>("pull-result", (e) => handler(e.payload)),
  onAuctions: (handler: (outcomes: AuctionOutcome[]) => void): Promise<UnlistenFn> =>
    listen<AuctionOutcome[]>("auction-result", (e) => handler(e.payload)),
  onUpdateAvailable: (handler: (version: string) => void): Promise<UnlistenFn> =>
    listen<string>("update-available", (e) => handler(e.payload)),
  onUpdateFailed: (handler: (error: string) => void): Promise<UnlistenFn> =>
    listen<string>("update-failed", (e) => handler(e.payload)),
};
