//! Prix de l'hôtel des ventes : l'addon NaowhForever garde le dernier scan complet dans son `SavedVariables`
//! (`ahPrices`, par hôtel : `prices`, `listed`, `time`). Le compagnon de qui en a le droit sur le site (le GM)
//! envoie chaque nouveau scan ; chez les autres, rien n'est lu ni envoyé. Notre addon n'y est pour rien.

use std::fs;
use std::path::{Path, PathBuf};

use regex::Regex;
use serde::Serialize;

use crate::api::SiteClient;
use crate::config::Config;
use crate::error::CoreError;

/// L'addon tiers dont on lit le scan (fichier `WTF/Account/<compte>/SavedVariables/NaowhForever.lua`).
pub const SCAN_ADDON: &str = "NaowhForever";

/// Le scan d'un hôtel des ventes : par objet, le prix le plus bas à l'unité (cuivre) et le nombre d'enchères.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HouseScan {
    /// Royaume et faction, tels que l'addon de scan les écrit.
    pub house: String,
    pub scanned_at: i64,
    /// (objet, prix, enchères), trié par objet.
    pub items: Vec<(u32, u64, Option<u32>)>,
}

/// Les fichiers du scan, un par compte WoW de l'installation.
pub fn find_scan_files(game_dir: &Path) -> Vec<PathBuf> {
    let mut found = Vec::new();
    let Ok(entries) = fs::read_dir(crate::wowdir::wtf_accounts_dir(game_dir)) else {
        return found;
    };
    for entry in entries.flatten() {
        let path = entry
            .path()
            .join("SavedVariables")
            .join(format!("{SCAN_ADDON}.lua"));
        if path.is_file() {
            found.push(path);
        }
    }
    found.sort();
    found
}

/// Extrait les scans du fichier sans interpréter le reste : le client écrit une entrée par ligne, on suit la
/// profondeur des accolades à partir de `["ahPrices"] = {`, quelle que soit la clé de la table ouverte (texte,
/// nombre, ou aucune) : une table inconnue est traversée sans rien y lire. Un bloc tronqué (fichier en cours
/// d'écriture) ne donne rien.
pub fn extract_scans(lua: &str) -> Vec<HouseScan> {
    let open = Regex::new(r#"^\s*(?:\[(?:"(.+)"|[^\]]+)\] = )?\{\s*$"#).unwrap();
    let close = Regex::new(r"^\s*\},?\s*(?:--.*)?$").unwrap();
    let pair = Regex::new(r"^\s*\[(\d+)\] = (\d+),").unwrap();
    let time = Regex::new(r#"^\s*\["time"\] = (\d+),"#).unwrap();

    struct Building {
        house: String,
        scanned_at: i64,
        prices: std::collections::BTreeMap<u32, u64>,
        listed: std::collections::HashMap<u32, u32>,
    }
    let mut scans = Vec::new();
    let mut depth = 0usize;
    let mut current: Option<Building> = None;
    let mut section = String::new();
    let mut complete = false;
    for line in lua.lines() {
        if depth == 0 {
            if line.trim_start().starts_with(r#"["ahPrices"] = {"#) {
                depth = 1;
            }
            continue;
        }
        if let Some(caps) = open.captures(line) {
            let key = caps.get(1).map(|m| m.as_str());
            if depth == 1 {
                current = key.map(|house| Building {
                    house: house.to_string(),
                    scanned_at: 0,
                    prices: Default::default(),
                    listed: Default::default(),
                });
            } else if depth == 2 {
                section = key.unwrap_or_default().to_string();
            }
            depth += 1;
        } else if close.is_match(line) {
            depth -= 1;
            match depth {
                2 => section.clear(),
                1 => {
                    if let Some(done) = current.take() {
                        if done.scanned_at > 0 && !done.prices.is_empty() {
                            scans.push(HouseScan {
                                house: done.house,
                                scanned_at: done.scanned_at,
                                items: done
                                    .prices
                                    .iter()
                                    .map(|(id, price)| (*id, *price, done.listed.get(id).copied()))
                                    .collect(),
                            });
                        }
                    }
                }
                0 => {
                    complete = true;
                    break;
                }
                _ => {}
            }
        } else if depth == 3 {
            let (Some(caps), Some(building)) = (pair.captures(line), current.as_mut()) else {
                continue;
            };
            let (Ok(id), Ok(value)) = (caps[1].parse::<u32>(), caps[2].parse::<u64>()) else {
                continue;
            };
            match section.as_str() {
                "prices" if value > 0 => {
                    building.prices.insert(id, value);
                }
                "listed" => {
                    building
                        .listed
                        .insert(id, u32::try_from(value).unwrap_or(u32::MAX));
                }
                _ => {}
            }
        } else if depth == 2 {
            if let (Some(caps), Some(building)) = (time.captures(line), current.as_mut()) {
                building.scanned_at = caps[1].parse().unwrap_or(0);
            }
        }
    }
    if complete {
        scans
    } else {
        Vec::new()
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum AuctionOutcome {
    /// Ce compte n'envoie pas les prix (réservé au GM) : aucun fichier n'a été lu.
    NotAllowed,
    Unchanged {
        house: String,
    },
    Sent {
        house: String,
        scanned_at: i64,
        items: usize,
    },
    /// Le site avait déjà ce scan (autre PC, compagnon réinstallé).
    Duplicate {
        house: String,
    },
    Failed {
        error: String,
    },
}

/// Un passage : s'il existe un fichier de scan et que le site autorise ce compte, envoie les scans plus récents
/// que le dernier envoyé. Met à jour `config.last_auction_scans` (à sauvegarder par l'appelant). Ne touche à
/// rien d'autre : un échec ici n'empêche jamais l'envoi des personnages.
pub fn upload_once(
    game_dir: &Path,
    config: &mut Config,
    client: &SiteClient,
) -> Vec<AuctionOutcome> {
    if !config.is_paired() {
        return Vec::new();
    }
    let files = find_scan_files(game_dir);
    if files.is_empty() {
        return Vec::new();
    }
    match client.auction_rights() {
        Ok(true) => {}
        Ok(false) => return vec![AuctionOutcome::NotAllowed],
        // Droit inconnu (site injoignable, jeton révoqué) : on ne dit rien, cette fonction n'existe pas pour qui
        // n'y a pas droit ; l'envoi des personnages signale déjà ces pannes.
        Err(e) => {
            log::warn!("hôtel des ventes : droit d'envoi inconnu ({e})");
            return Vec::new();
        }
    }
    let mut outcomes = Vec::new();
    for file in files {
        let text = match fs::read(&file) {
            Ok(bytes) => String::from_utf8_lossy(&bytes).into_owned(),
            Err(e) => {
                outcomes.push(AuctionOutcome::Failed {
                    error: e.to_string(),
                });
                continue;
            }
        };
        for scan in extract_scans(&text) {
            let house = scan.house.clone();
            let known = config.last_auction_scans.get(&house).copied().unwrap_or(0);
            if scan.scanned_at <= known {
                outcomes.push(AuctionOutcome::Unchanged { house });
                continue;
            }
            match client.upload_auctions(&scan) {
                Ok(()) => {
                    config
                        .last_auction_scans
                        .insert(house.clone(), scan.scanned_at);
                    outcomes.push(AuctionOutcome::Sent {
                        house,
                        scanned_at: scan.scanned_at,
                        items: scan.items.len(),
                    });
                }
                Err(CoreError::Duplicate) => {
                    config
                        .last_auction_scans
                        .insert(house.clone(), scan.scanned_at);
                    outcomes.push(AuctionOutcome::Duplicate { house });
                }
                Err(e) => outcomes.push(AuctionOutcome::Failed {
                    error: format!("{house} : {e}"),
                }),
            }
        }
    }
    outcomes
}

#[cfg(test)]
mod tests {
    use super::*;
    use httpmock::prelude::*;

    const SAMPLE: &str = r#"
NaowhForeverDB = {
["profiles"] = {
["Default"] = {
["ahPrices"] = true,
["prices"] = {
[1] = 2,
},
},
},
["account"] = {
["ahPrices"] = {
["Forever-Alliance"] = {
["prices"] = {
[15347] = 2000,
[2589] = 100,
[7363] = 600,
},
["requested"] = 1794342462,
["time"] = 1794342484,
["listed"] = {
[15347] = 8,
[2589] = 71,
},
["history"] = {
{
[2589] = 1,
}, -- [1]
[7] = {
["prices"] = {
[2589] = 2,
},
},
},
},
[3] = {
["prices"] = {
[2589] = 3,
},
["time"] = 5,
},
["Forever-Horde"] = {
["requested"] = 1794342000,
},
},
["welcomeSeen"] = true,
},
}
"#;

    fn game_with_scan(tmp: &Path, text: &str) {
        let dir = tmp.join("WTF/Account/WOW1/SavedVariables");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("NaowhForever.lua"), text).unwrap();
    }

    #[test]
    fn extracts_each_scanned_house_and_ignores_the_rest_of_the_file() {
        let scans = extract_scans(SAMPLE);
        assert_eq!(
            scans,
            vec![HouseScan {
                house: "Forever-Alliance".into(),
                scanned_at: 1794342484,
                // Triés par objet ; un objet sans compte d'enchères reste envoyé.
                items: vec![
                    (2589, 100, Some(71)),
                    (7363, 600, None),
                    (15347, 2000, Some(8))
                ],
            }]
        );
        assert!(extract_scans("NaowhForeverDB = {\n[\"ahPrices\"] = true,\n}\n").is_empty());
        // Fichier coupé pendant l'écriture : rien, on réessaiera au prochain changement.
        let cut = &SAMPLE[..SAMPLE.find("[\"welcomeSeen\"]").unwrap() - 3];
        assert!(extract_scans(cut).is_empty());
    }

    fn status(server: &MockServer, allowed: bool) -> httpmock::Mock<'_> {
        server.mock(|when, then| {
            when.method(GET)
                .path("/api/sync/auctions/rights/")
                .header("Authorization", "Companion tok");
            then.status(200)
                .json_body(serde_json::json!({ "upload": allowed }));
        })
    }

    #[test]
    fn unknown_rights_stay_silent() {
        let tmp = tempfile::tempdir().unwrap();
        game_with_scan(tmp.path(), SAMPLE);
        let mut config = Config::default();
        config.token = Some("tok".into());
        // Site injoignable : rien à afficher, rien d'envoyé.
        let down = SiteClient::new("http://127.0.0.1:9", Some("tok".into()));
        assert!(upload_once(tmp.path(), &mut config, &down).is_empty());
        // Site plus ancien, sans cette fonction : pas de droit.
        let server = MockServer::start();
        server.mock(|when, then| {
            when.method(GET).path("/api/sync/auctions/rights/");
            then.status(404);
        });
        let old = SiteClient::new(&server.base_url(), Some("tok".into()));
        assert_eq!(
            upload_once(tmp.path(), &mut config, &old),
            vec![AuctionOutcome::NotAllowed]
        );
    }

    #[test]
    fn sends_a_new_scan_once_when_the_site_allows_it() {
        let tmp = tempfile::tempdir().unwrap();
        game_with_scan(tmp.path(), SAMPLE);
        let server = MockServer::start();
        status(&server, true);
        let upload = server.mock(|when, then| {
            when.method(POST)
                .path("/api/sync/auctions/")
                .header("Authorization", "Companion tok")
                .json_body(serde_json::json!({
                    "house": "Forever-Alliance", "scanned_at": 1794342484,
                    "items": [[2589, 100, 71], [7363, 600, null], [15347, 2000, 8]]
                }));
            then.status(201).json_body(serde_json::json!({ "id": 1 }));
        });
        let client = SiteClient::new(&server.base_url(), Some("tok".into()));
        let mut config = Config::default();
        assert!(upload_once(tmp.path(), &mut config, &client).is_empty()); // pas appairé
        config.token = Some("tok".into());
        assert_eq!(
            upload_once(tmp.path(), &mut config, &client),
            vec![AuctionOutcome::Sent {
                house: "Forever-Alliance".into(),
                scanned_at: 1794342484,
                items: 3
            }]
        );
        assert_eq!(
            upload_once(tmp.path(), &mut config, &client),
            vec![AuctionOutcome::Unchanged {
                house: "Forever-Alliance".into()
            }]
        );
        assert_eq!(upload.hits(), 1);
    }

    #[test]
    fn members_never_read_nor_send_anything() {
        let tmp = tempfile::tempdir().unwrap();
        game_with_scan(tmp.path(), SAMPLE);
        let server = MockServer::start();
        status(&server, false);
        let upload = server.mock(|when, then| {
            when.method(POST).path("/api/sync/auctions/");
            then.status(403);
        });
        let client = SiteClient::new(&server.base_url(), Some("tok".into()));
        let mut config = Config::default();
        config.token = Some("tok".into());
        assert_eq!(
            upload_once(tmp.path(), &mut config, &client),
            vec![AuctionOutcome::NotAllowed]
        );
        assert_eq!(upload.hits(), 0);
        assert!(config.last_auction_scans.is_empty());
    }

    #[test]
    fn no_scan_addon_means_no_call_to_the_site_at_all() {
        let tmp = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(tmp.path().join("WTF/Account/WOW1/SavedVariables")).unwrap();
        let server = MockServer::start();
        let me = status(&server, true);
        let client = SiteClient::new(&server.base_url(), Some("tok".into()));
        let mut config = Config::default();
        config.token = Some("tok".into());
        assert!(upload_once(tmp.path(), &mut config, &client).is_empty());
        assert_eq!(me.hits(), 0);
    }

    #[test]
    fn already_known_scan_is_remembered_and_site_errors_are_retried() {
        let tmp = tempfile::tempdir().unwrap();
        game_with_scan(tmp.path(), SAMPLE);
        let server = MockServer::start();
        status(&server, true);
        let mut refused = server.mock(|when, then| {
            when.method(POST).path("/api/sync/auctions/");
            then.status(500);
        });
        let client = SiteClient::new(&server.base_url(), Some("tok".into()));
        let mut config = Config::default();
        config.token = Some("tok".into());
        assert!(matches!(
            upload_once(tmp.path(), &mut config, &client)[0],
            AuctionOutcome::Failed { .. }
        ));
        assert!(config.last_auction_scans.is_empty()); // on réessaiera
        refused.delete();
        server.mock(|when, then| {
            when.method(POST).path("/api/sync/auctions/");
            then.status(409)
                .json_body(serde_json::json!({ "detail": "Ce scan a déjà été reçu." }));
        });
        assert_eq!(
            upload_once(tmp.path(), &mut config, &client),
            vec![AuctionOutcome::Duplicate {
                house: "Forever-Alliance".into()
            }]
        );
        assert_eq!(config.last_auction_scans["Forever-Alliance"], 1794342484);
    }
}
