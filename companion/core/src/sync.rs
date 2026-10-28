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

#[cfg(test)]
mod tests {
    use super::*;
    use httpmock::prelude::*;

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
