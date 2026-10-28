//! Application Tauri : fine couche au-dessus de `companion-core`. État partagé, commandes pour l'interface,
//! surveillance du fichier SavedVariables, icône de barre des tâches, mise à jour.

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use companion_core::api::SiteClient;
use companion_core::config::{default_dir, Config};
use companion_core::sync::{sync_once, SyncOutcome};
use companion_core::{addon, savedvars, wowdir};
use notify::{RecursiveMode, Watcher};
use serde::{Deserialize, Serialize};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Emitter, Manager, State};

struct Inner {
    config_dir: PathBuf,
    config: Config,
    last_sync: Option<Vec<SyncOutcome>>,
    last_sync_at: Option<String>,
}

type Shared = Arc<Mutex<Inner>>;

#[derive(Serialize)]
struct AppState {
    version: String,
    addon_version: String,
    site_url: String,
    game_dir: Option<String>,
    device_name: String,
    paired: bool,
    display_name: Option<String>,
    autostart: bool,
    accounts: Vec<String>,
    installed_addon_version: Option<String>,
    last_sync: Option<Vec<SyncOutcome>>,
    last_sync_at: Option<String>,
    candidates: Vec<String>,
}

fn now_iso() -> String {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("{secs}")
}

fn snapshot(inner: &Inner) -> AppState {
    let config = &inner.config;
    let game_dir = config.game_dir.clone();
    AppState {
        version: env!("CARGO_PKG_VERSION").to_string(),
        addon_version: addon::embedded_version(),
        site_url: config.site_url.clone(),
        game_dir: game_dir.as_ref().map(|p| p.display().to_string()),
        device_name: config.device_name.clone(),
        paired: config.is_paired(),
        display_name: config.display_name.clone(),
        autostart: config.autostart,
        accounts: game_dir
            .as_deref()
            .map(|g| {
                savedvars::find_saved_variables(g)
                    .into_iter()
                    .map(|f| f.account)
                    .collect()
            })
            .unwrap_or_default(),
        installed_addon_version: game_dir
            .as_deref()
            .and_then(|g| addon::installed_version(&wowdir::addons_dir(g))),
        last_sync: inner.last_sync.clone(),
        last_sync_at: inner.last_sync_at.clone(),
        candidates: if game_dir.is_none() {
            wowdir::candidates()
                .iter()
                .map(|p| p.display().to_string())
                .collect()
        } else {
            vec![]
        },
    }
}

fn client_for(config: &Config) -> SiteClient {
    SiteClient::new(&config.site_url, config.token.clone())
}

fn save(inner: &Inner) -> Result<(), String> {
    inner
        .config
        .save_to(&inner.config_dir)
        .map_err(|e| e.to_string())
}

fn run_sync(app: &AppHandle, shared: &Shared) -> Vec<SyncOutcome> {
    let (game_dir, mut config) = {
        let inner = shared.lock().unwrap();
        (inner.config.game_dir.clone(), inner.config.clone())
    };
    let Some(game_dir) = game_dir else {
        return vec![];
    };
    if !config.is_paired() {
        return vec![];
    }
    let client = client_for(&config);
    let outcomes = sync_once(&game_dir, &mut config, &client);
    {
        let mut inner = shared.lock().unwrap();
        inner.config.last_fingerprints = config.last_fingerprints;
        inner.last_sync = Some(outcomes.clone());
        inner.last_sync_at = Some(now_iso());
        let _ = save(&inner);
    }
    let _ = app.emit("sync-result", &outcomes);
    outcomes
}

// --- commandes -------------------------------------------------------------------------------------

#[tauri::command]
fn get_state(shared: State<Shared>) -> AppState {
    snapshot(&shared.lock().unwrap())
}

#[tauri::command]
fn set_game_dir(app: AppHandle, shared: State<Shared>, path: String) -> Result<AppState, String> {
    let mut inner = shared.lock().unwrap();
    if path.is_empty() {
        inner.config.game_dir = None;
    } else {
        log::info!("dossier choisi : {path}");
        let dir = wowdir::normalize(Path::new(&path)).ok_or_else(|| {
            format!("« {path} » ne ressemble pas à une installation de World of Warcraft (ni ce dossier, ni _forever_ dedans).")
        })?;
        addon::install(&wowdir::addons_dir(&dir), false)
            .map_err(|e| format!("Installation de l'addon : {e}"))?;
        inner.config.game_dir = Some(dir);
    }
    save(&inner)?;
    drop(inner);
    restart_watcher(&app, shared.inner().clone());
    Ok(snapshot(&shared.lock().unwrap()))
}

#[tauri::command]
fn pair(
    app: AppHandle,
    shared: State<Shared>,
    code: String,
    device_name: String,
) -> Result<AppState, String> {
    let (site_url, name) = {
        let inner = shared.lock().unwrap();
        (
            inner.config.site_url.clone(),
            if device_name.trim().is_empty() {
                inner.config.device_name.clone()
            } else {
                device_name
            },
        )
    };
    let response = SiteClient::new(&site_url, None)
        .pair(&code, &name)
        .map_err(|e| e.to_string())?;
    {
        let mut inner = shared.lock().unwrap();
        inner.config.token = Some(response.token);
        inner.config.display_name = Some(response.display_name);
        inner.config.device_name = name;
        inner.config.last_fingerprints.clear();
        save(&inner)?;
    }
    let shared_clone = shared.inner().clone();
    std::thread::spawn(move || {
        let _ = run_sync(&app, &shared_clone);
    });
    Ok(snapshot(&shared.lock().unwrap()))
}

#[tauri::command]
fn unpair(shared: State<Shared>) -> Result<AppState, String> {
    let mut inner = shared.lock().unwrap();
    inner.config.token = None;
    inner.config.display_name = None;
    inner.config.last_fingerprints.clear();
    save(&inner)?;
    Ok(snapshot(&inner))
}

#[tauri::command]
fn sync_now(app: AppHandle, shared: State<Shared>) -> Vec<SyncOutcome> {
    run_sync(&app, shared.inner())
}

#[tauri::command]
fn install_addon(shared: State<Shared>) -> Result<String, String> {
    let inner = shared.lock().unwrap();
    let game_dir = inner
        .config
        .game_dir
        .clone()
        .ok_or("Choisis d'abord le dossier du jeu.")?;
    match addon::install(&wowdir::addons_dir(&game_dir), true).map_err(|e| e.to_string())? {
        addon::InstallOutcome::Installed { version } => Ok(format!(
            "Addon {version} installé. Reconnecte-toi ou fais /reload."
        )),
        addon::InstallOutcome::Updated { to, .. } => Ok(format!(
            "Addon mis à jour en {to}. Reconnecte-toi ou fais /reload."
        )),
        addon::InstallOutcome::UpToDate { version } => Ok(format!("Addon {version} réinstallé.")),
    }
}

#[derive(Deserialize)]
struct Settings {
    autostart: Option<bool>,
    site_url: Option<String>,
}

#[tauri::command]
fn set_settings(
    app: AppHandle,
    shared: State<Shared>,
    settings: Settings,
) -> Result<AppState, String> {
    let mut inner = shared.lock().unwrap();
    if let Some(on) = settings.autostart {
        inner.config.autostart = on;
        apply_autostart(&app, on);
    }
    if let Some(url) = settings.site_url {
        inner.config.site_url = url.trim().trim_end_matches('/').to_string();
    }
    save(&inner)?;
    Ok(snapshot(&inner))
}

#[tauri::command]
fn open_site(shared: State<Shared>, path: String) -> Result<(), String> {
    let url = format!("{}{}", shared.lock().unwrap().config.site_url, path);
    tauri_plugin_opener::open_url(url, None::<&str>).map_err(|e| e.to_string())
}

fn apply_autostart(app: &AppHandle, on: bool) {
    use tauri_plugin_autostart::ManagerExt;
    let manager = app.autolaunch();
    let _ = if on {
        manager.enable()
    } else {
        manager.disable()
    };
}

// --- surveillance du fichier et du journal de chat ----------------------------------------------------

struct WatcherSlot(Mutex<Option<notify::RecommendedWatcher>>);

fn restart_watcher(app: &AppHandle, shared: Shared) {
    let game_dir = shared.lock().unwrap().config.game_dir.clone();
    let slot = app.state::<WatcherSlot>();
    let mut guard = slot.0.lock().unwrap();
    *guard = None;
    let Some(game_dir) = game_dir else { return };
    let accounts = wowdir::wtf_accounts_dir(&game_dir);
    let _ = std::fs::create_dir_all(&accounts);
    let app_handle = app.clone();
    let debounce: Arc<Mutex<Option<Instant>>> = Arc::new(Mutex::new(None));
    let watcher = notify::recommended_watcher(move |event: notify::Result<notify::Event>| {
        let Ok(event) = event else { return };
        let concerns_addon = event.paths.iter().any(|p| {
            p.file_name()
                .and_then(|n| n.to_str())
                .map(|n| n.starts_with(savedvars::ADDON_NAME))
                .unwrap_or(false)
        });
        if !concerns_addon {
            return;
        }
        // Le client écrit le fichier en plusieurs fois : on attend deux secondes de calme.
        let mut pending = debounce.lock().unwrap();
        let already = pending.is_some();
        *pending = Some(Instant::now());
        if already {
            return;
        }
        let app = app_handle.clone();
        let debounce = debounce.clone();
        let shared = shared.clone();
        std::thread::spawn(move || {
            loop {
                std::thread::sleep(Duration::from_secs(2));
                let last = debounce.lock().unwrap().unwrap_or_else(Instant::now);
                if last.elapsed() >= Duration::from_secs(2) {
                    break;
                }
            }
            *debounce.lock().unwrap() = None;
            let _ = run_sync(&app, &shared);
        });
    });
    match watcher {
        Ok(mut w) => {
            if let Err(e) = w.watch(&accounts, RecursiveMode::Recursive) {
                log::warn!("surveillance impossible de {}: {e}", accounts.display());
            }
            *guard = Some(w);
        }
        Err(e) => log::warn!("surveillance impossible : {e}"),
    }
}

// --- démarrage ---------------------------------------------------------------------------------------

pub fn run() {
    env_logger::init();
    let config_dir = default_dir().expect("dossier de configuration");
    let config = Config::load_from(&config_dir).unwrap_or_default();
    let shared: Shared = Arc::new(Mutex::new(Inner {
        config_dir,
        config,
        last_sync: None,
        last_sync_at: None,
    }));

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .manage(shared.clone())
        .manage(WatcherSlot(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            get_state,
            set_game_dir,
            pair,
            unpair,
            sync_now,
            install_addon,
            set_settings,
            open_site
        ])
        .setup(move |app| {
            let handle = app.handle().clone();
            // Barre des tâches : ouvrir, synchroniser, quitter. Fermer la fenêtre la cache seulement.
            let open = MenuItem::with_id(app, "open", "Ouvrir", true, None::<&str>)?;
            let sync =
                MenuItem::with_id(app, "sync", "Synchroniser maintenant", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quitter", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &sync, &quit])?;
            let shared_tray = shared.clone();
            TrayIconBuilder::new()
                .icon(app.default_window_icon().cloned().expect("icône"))
                .menu(&menu)
                .tooltip("WoW Forever Guilde")
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "open" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "sync" => {
                        let _ = run_sync(app, &shared_tray);
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            if let Some(window) = app.get_webview_window("main") {
                let w = window.clone();
                window.on_window_event(move |event| {
                    if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        let _ = w.hide();
                    }
                });
            }
            let autostart = shared.lock().unwrap().config.autostart;
            apply_autostart(&handle, autostart);
            restart_watcher(&handle, shared.clone());
            // Premier passage au démarrage : on rattrape ce qui a été écrit pendant que le compagnon était fermé.
            let shared_boot = shared.clone();
            let boot = handle.clone();
            std::thread::spawn(move || {
                std::thread::sleep(Duration::from_secs(2));
                if let Some(game_dir) = shared_boot.lock().unwrap().config.game_dir.clone() {
                    let _ = addon::install(&wowdir::addons_dir(&game_dir), false);
                }
                let _ = run_sync(&boot, &shared_boot);
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("lancement du compagnon");
}
