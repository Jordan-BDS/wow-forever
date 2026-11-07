//! La boucle du compagnon : pour chaque compte WoW, lire le code d'export, comparer son empreinte au dernier
//! envoi, l'envoyer au site, mémoriser le résultat. Appelée au démarrage et à chaque changement de fichier.

use std::path::Path;

use serde::Serialize;

use crate::api::SiteClient;
use crate::config::Config;
use crate::error::CoreError;
use crate::savedvars::{find_saved_variables, fingerprint, read_export};

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum SyncOutcome {
    /// Rien à envoyer : fichier absent, pas de code, ou code identique au dernier envoi.
    Unchanged {
        account: String,
    },
    Sent {
        account: String,
        summary: String,
        characters: Vec<String>,
    },
    Duplicate {
        account: String,
    },
    Failed {
        account: String,
        error: String,
    },
}

/// Un passage complet sur une installation. Met à jour `config.last_fingerprints` (à sauvegarder par l'appelant).
pub fn sync_once(game_dir: &Path, config: &mut Config, client: &SiteClient) -> Vec<SyncOutcome> {
    let mut outcomes = Vec::new();
    for file in find_saved_variables(game_dir) {
        let account = file.account.clone();
        let export = match read_export(&file.path) {
            Ok(Some(export)) => export,
            Ok(None) => {
                outcomes.push(SyncOutcome::Unchanged { account });
                continue;
            }
            Err(e) => {
                outcomes.push(SyncOutcome::Failed {
                    account,
                    error: e.to_string(),
                });
                continue;
            }
        };
        let print = fingerprint(&export.code);
        if config.last_fingerprints.get(&account) == Some(&print) {
            outcomes.push(SyncOutcome::Unchanged { account });
            continue;
        }
        match client.import(&export.code) {
            Ok(batch) => {
                config.last_fingerprints.insert(account.clone(), print);
                let characters = batch
                    .snapshots
                    .iter()
                    .map(|s| format!("{} : {}", s.full_name, s.status))
                    .collect();
                outcomes.push(SyncOutcome::Sent {
                    account,
                    summary: batch.summary.describe(),
                    characters,
                });
            }
            Err(CoreError::Duplicate) => {
                config.last_fingerprints.insert(account.clone(), print);
                outcomes.push(SyncOutcome::Duplicate { account });
            }
            Err(e) => outcomes.push(SyncOutcome::Failed {
                account,
                error: e.to_string(),
            }),
        }
    }
    outcomes
}

/// Le sens inverse : le site complète l'addon de ce PC (voir `seed`).
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum PullOutcome {
    /// Le jeu tourne : le fichier serait écrasé à la déconnexion, on réessaiera au prochain lancement.
    GameRunning,
    /// Rien à écrire : pas appairé, aucun personnage sur le site, aucun compte WoW sur ce PC.
    Nothing {
        reason: String,
    },
    Completed {
        accounts: Vec<String>,
        characters: usize,
        /// Fichiers créés (PC neuf, jamais connecté avec l'addon).
        created: Vec<String>,
    },
    Failed {
        error: String,
    },
}

/// Recopie l'état du site dans le fichier de l'addon de chaque compte WoW, jeu fermé. À appeler après
/// `sync_once` (ce PC a d'abord envoyé ce qu'il avait), au lancement du compagnon.
pub fn pull_once(game_dir: &Path, config: &Config, client: &SiteClient) -> PullOutcome {
    pull_with(game_dir, config, client, crate::wowdir::game_running)
}

pub fn pull_with(
    game_dir: &Path,
    config: &Config,
    client: &SiteClient,
    running: impl Fn(&Path) -> bool,
) -> PullOutcome {
    if !config.is_paired() {
        return PullOutcome::Nothing {
            reason: "compagnon non lié au site".into(),
        };
    }
    if running(game_dir) {
        return PullOutcome::GameRunning;
    }
    let state = match client.state() {
        Ok(state) => state,
        Err(e) => {
            return PullOutcome::Failed {
                error: e.to_string(),
            }
        }
    };
    if state.characters.is_empty() {
        return PullOutcome::Nothing {
            reason: "aucun personnage connu du site".into(),
        };
    }
    let files = crate::wowdir::account_files(game_dir);
    if files.is_empty() {
        return PullOutcome::Nothing {
            reason: "aucun compte WoW dans WTF/Account (connecte-toi une fois au jeu)".into(),
        };
    }
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let mut accounts = Vec::new();
    let mut created = Vec::new();
    let mut characters = 0;
    for (account, path) in files {
        match crate::seed::complete_file(&path, &state, now) {
            Ok(done) => {
                characters = done.characters;
                if done.created {
                    created.push(account.clone());
                }
                accounts.push(account);
            }
            Err(e) => {
                return PullOutcome::Failed {
                    error: format!("{account} : {e}"),
                }
            }
        }
    }
    PullOutcome::Completed {
        accounts,
        characters,
        created,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use httpmock::prelude::*;

    fn state_json() -> serde_json::Value {
        serde_json::json!({
            "seed_at": 1764200000,
            "characters": [{
                "guid": "Player-1-T", "name": "Thrall", "class": "SHAMAN", "race": "Orc", "level": 60,
                "counting_since": 1764000000, "counters": { "deaths": 16 }, "journal": {}, "events": [],
                "mobs": {}, "pvp": {}, "played": null, "previous_guids": [], "bases": { "pc-fixe": 1764000600 }
            }]
        })
    }

    #[test]
    fn pull_completes_every_account_unless_the_game_runs() {
        let tmp = tempfile::tempdir().unwrap();
        game_with_export(tmp.path(), "WFG1:00000000:AAAA"); // compte WOW1 avec un fichier
        std::fs::create_dir_all(tmp.path().join("WTF/Account/WOW2")).unwrap(); // compte sans fichier
        let server = MockServer::start();
        let state = server.mock(|when, then| {
            when.method(GET)
                .path("/api/sync/state/")
                .header("Authorization", "Companion tok");
            then.status(200).json_body(state_json());
        });
        let client = SiteClient::new(&server.base_url(), Some("tok".into()));
        let mut config = Config::default();
        assert!(matches!(
            pull_with(tmp.path(), &config, &client, |_| false),
            PullOutcome::Nothing { .. }
        ));
        config.token = Some("tok".into());
        assert_eq!(
            pull_with(tmp.path(), &config, &client, |_| true),
            PullOutcome::GameRunning
        );
        assert_eq!(state.hits(), 0);
        let outcome = pull_with(tmp.path(), &config, &client, |_| false);
        assert_eq!(
            outcome,
            PullOutcome::Completed {
                accounts: vec!["WOW1".into(), "WOW2".into()],
                characters: 1,
                created: vec!["WOW2".into()],
            }
        );
        let written = std::fs::read_to_string(
            tmp.path()
                .join("WTF/Account/WOW1/SavedVariables/WoWForeverGuilde.lua"),
        )
        .unwrap();
        assert!(written.contains("[\"export\"] = \"WFG1:00000000:AAAA\"")); // l'export en attente est intact
        assert!(
            written.contains("[\"seed\"] = {") && written.contains("[\"pc-fixe\"] = 1764000600")
        );
        assert!(tmp
            .path()
            .join("WTF/Account/WOW2/SavedVariables/WoWForeverGuilde.lua")
            .is_file());
        // Le code d'export en attente se relit tel quel après la réécriture du fichier.
        let files = find_saved_variables(tmp.path());
        assert_eq!(
            read_export(&files[0].path).unwrap().unwrap().code,
            "WFG1:00000000:AAAA"
        );
    }

    #[test]
    fn pull_reports_site_errors() {
        let tmp = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(tmp.path().join("WTF/Account/WOW1")).unwrap();
        let client = SiteClient::new("http://127.0.0.1:9", Some("tok".into()));
        let mut config = Config::default();
        config.token = Some("tok".into());
        assert!(matches!(
            pull_with(tmp.path(), &config, &client, |_| false),
            PullOutcome::Failed { .. }
        ));
    }

    fn game_with_export(tmp: &Path, code: &str) {
        let dir = tmp.join("WTF/Account/WOW1/SavedVariables");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(
            dir.join("WoWForeverGuilde.lua"),
            format!("WoWForeverGuildeDB = {{\n\t[\"export_at\"] = 1,\n\t[\"export\"] = \"{code}\",\n}}\n"),
        )
        .unwrap();
    }

    #[test]
    fn sends_once_then_unchanged_then_again_after_change() {
        let tmp = tempfile::tempdir().unwrap();
        game_with_export(tmp.path(), "WFG1:00000000:AAAA");
        let server = MockServer::start();
        let import = server.mock(|when, then| {
            when.method(POST).path("/api/sync/import/");
            then.status(201).json_body(serde_json::json!({
                "id": 1, "received_at": "x", "summary": { "created": 1 },
                "snapshots": [{ "full_name": "Thrall Fils-de-Durotan", "status": "created" }]
            }));
        });
        let client = SiteClient::new(&server.base_url(), Some("tok".into()));
        let mut config = Config::default();

        let first = sync_once(tmp.path(), &mut config, &client);
        assert_eq!(
            first,
            vec![SyncOutcome::Sent {
                account: "WOW1".into(),
                summary: "1 créé".into(),
                characters: vec!["Thrall Fils-de-Durotan : created".into()],
            }]
        );
        assert_eq!(
            sync_once(tmp.path(), &mut config, &client),
            vec![SyncOutcome::Unchanged {
                account: "WOW1".into()
            }]
        );
        game_with_export(tmp.path(), "WFG1:00000000:BBBB");
        assert!(matches!(
            sync_once(tmp.path(), &mut config, &client)[0],
            SyncOutcome::Sent { .. }
        ));
        assert_eq!(import.hits(), 2);
    }

    #[test]
    fn site_down_is_reported_and_retried_later() {
        let tmp = tempfile::tempdir().unwrap();
        game_with_export(tmp.path(), "WFG1:00000000:AAAA");
        let client = SiteClient::new("http://127.0.0.1:9", Some("tok".into()));
        let mut config = Config::default();
        assert!(matches!(
            sync_once(tmp.path(), &mut config, &client)[0],
            SyncOutcome::Failed { .. }
        ));
        assert!(config.last_fingerprints.is_empty()); // on réessaiera
    }
}
