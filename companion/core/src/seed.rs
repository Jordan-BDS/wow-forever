//! Complétion de l'addon depuis le site : l'état fusionné de chaque personnage (toutes installations) est
//! recopié dans `SavedVariables`, jeu fermé, avec une marque `seed` qui dit ce que ce fichier contient déjà
//! des autres installations (le site ne compte ensuite de celles-ci que ce qu'elles font après).

use std::fs;
use std::path::Path;

use crate::api::{SiteState, StateCharacter};
use crate::error::{CoreError, Result};
use crate::luatable::{from_json, parse_file, write_file, Key, Table, Value};

pub const DB_NAME: &str = "WoWForeverGuildeDB";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Completion {
    pub characters: usize,
    /// Le fichier n'existait pas (PC neuf) : créé.
    pub created: bool,
}

fn num(value: Option<serde_json::Value>) -> Option<f64> {
    value.and_then(|v| v.as_f64())
}

/// Applique l'état du site à l'entrée d'un personnage, sans toucher à ce que le site ne connaît pas
/// (équipement, métiers, réglages de l'addon…).
fn complete_entry(entry: &mut Table, state: &StateCharacter, seed_at: i64, now: i64) {
    let set_if_missing = |entry: &mut Table, key: &str, value: Option<Value>| {
        if entry.get(key).is_none() {
            if let Some(v) = value {
                entry.set(key, v);
            }
        }
    };
    set_if_missing(entry, "guid", Some(Value::Str(state.guid.clone())));
    set_if_missing(
        entry,
        "name",
        state.name.clone().filter(|s| !s.is_empty()).map(Value::Str),
    );
    set_if_missing(
        entry,
        "surname",
        state
            .surname
            .clone()
            .filter(|s| !s.is_empty())
            .map(Value::Str),
    );
    set_if_missing(
        entry,
        "realm",
        state
            .realm
            .clone()
            .filter(|s| !s.is_empty())
            .map(Value::Str),
    );
    set_if_missing(
        entry,
        "class",
        state
            .class
            .clone()
            .filter(|s| !s.is_empty())
            .map(Value::Str),
    );
    set_if_missing(
        entry,
        "race",
        state.race.clone().filter(|s| !s.is_empty()).map(Value::Str),
    );
    set_if_missing(entry, "level", state.level.map(|n| Value::Num(n as f64)));
    set_if_missing(entry, "created_at", Some(Value::Num(now as f64)));
    set_if_missing(entry, "updated_at", Some(Value::Num(now as f64)));

    // Ce qui se cumule : l'état du site remplace, il contient déjà ce fichier.
    for (key, value) in [
        ("counters", &state.counters),
        ("journal", &state.journal),
        ("events", &state.events),
        ("mobs", &state.mobs),
        ("previous_guids", &state.previous_guids),
    ] {
        match from_json(value) {
            Some(Value::Table(t)) => entry.set(key, Value::Table(t)),
            _ => entry.set(key, Value::Table(Table::default())),
        }
    }
    if let Some(since) = state.counting_since {
        let local = entry.get_num("counting_since").unwrap_or(f64::INFINITY);
        entry.set("counting_since", Value::Num(local.min(since as f64)));
    }
    // Totaux du jeu : le plus grand des deux.
    if let Some(played) = state.played {
        let local = entry.get_num("played").unwrap_or(0.0);
        entry.set("played", Value::Num(local.max(played as f64)));
    }
    let site_pvp = state.pvp.as_object().cloned().unwrap_or_default();
    let pvp = entry.table_mut("pvp");
    if let Some(bg) = site_pvp.get("bg").and_then(from_json) {
        pvp.set("bg", bg);
    }
    if let Some(hk) = num(site_pvp.get("hk_lifetime").cloned()) {
        let local = pvp.get_num("hk_lifetime").unwrap_or(0.0);
        pvp.set("hk_lifetime", Value::Num(local.max(hk)));
    }
    for key in ["rank", "honor", "honor_level"] {
        if pvp.get(key).is_none() {
            if let Some(v) = site_pvp.get(key).and_then(from_json) {
                pvp.set(key, v);
            }
        }
    }
    // La marque : ce fichier contient chaque installation jusqu'à l'export indiqué.
    let mut bases = Table::default();
    for (install, at) in &state.bases {
        bases
            .entries
            .push((Key::Str(install.clone()), Value::Num(*at as f64)));
    }
    let mut seed = Table::default();
    seed.set("at", Value::Num(seed_at as f64));
    seed.set("bases", Value::Table(bases));
    entry.set("seed", Value::Table(seed));
}

/// Complète (ou crée) le fichier `SavedVariables` d'un compte WoW avec l'état du site. Écriture atomique.
pub fn complete_file(path: &Path, state: &SiteState, now: i64) -> Result<Completion> {
    let existing = match fs::read_to_string(path) {
        Ok(text) => Some(text),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
        Err(e) => return Err(e.into()),
    };
    let created = existing.is_none();
    let mut assignments = match &existing {
        Some(text) => {
            parse_file(text).map_err(|e| CoreError::Parse(format!("{} : {e}", path.display())))?
        }
        None => Vec::new(),
    };
    if !assignments.iter().any(|(name, _)| name == DB_NAME) {
        assignments.push((DB_NAME.to_string(), Value::Table(Table::default())));
    }
    let db = assignments
        .iter_mut()
        .find(|(name, _)| name == DB_NAME)
        .map(|(_, v)| v)
        .expect("table ajoutée juste avant");
    let Value::Table(db) = db else {
        return Err(CoreError::Parse(format!(
            "{} : {DB_NAME} n'est pas une table",
            path.display()
        )));
    };
    let characters = db.table_mut("characters");
    for character in &state.characters {
        let entry = characters.table_mut(&character.guid);
        complete_entry(entry, character, state.seed_at, now);
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("lua.tmp");
    fs::write(&tmp, write_file(&assignments))?;
    fs::rename(&tmp, path)?;
    Ok(Completion {
        characters: state.characters.len(),
        created,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::luatable::parse_file;

    const EXISTING: &str = r#"
WoWForeverGuildeDB = {
	["version"] = 1,
	["installId"] = "portable1",
	["settings"] = {
		["sharePlaytime"] = true,
	},
	["characters"] = {
		["Player-1-T"] = {
			["guid"] = "Player-1-T",
			["name"] = "Thrall",
			["class"] = "SHAMAN",
			["counting_since"] = 1764100000,
			["counters"] = {
				["deaths"] = 2,
			},
			["journal"] = {
			},
			["gear"] = {
				["head"] = {
					["id"] = 16842,
				},
			},
			["pvp"] = {
				["hk_lifetime"] = 50,
				["rank"] = 3,
			},
			["professions"] = {
				["171"] = {
					["id"] = 171,
					["recipes"] = {
						17580,
					},
				},
			},
		},
	},
}
"#;

    fn state() -> SiteState {
        serde_json::from_value(serde_json::json!({
            "seed_at": 1764200000,
            "characters": [
                {
                    "guid": "Player-1-T", "name": "Thrall", "surname": "Fils-de-Durotan", "realm": "Forever",
                    "class": "SHAMAN", "race": "Orc", "level": 60, "counting_since": 1764000000,
                    "counters": { "deaths": 16, "kills": 125, "gathering": { "mining": 325 } },
                    "journal": { "2026-09-20": { "deaths": 10 } },
                    "events": [ { "k": "death", "t": 1764000500, "zone": "Durotar" } ],
                    "mobs": { "299": { "n": 75, "name": "Loup", "first": 1763990000, "last": 1764000400 } },
                    "pvp": { "hk_lifetime": 2340, "rank": 8, "bg": { "Goulet": { "played": 13, "won": 10 } } },
                    "played": 123456, "previous_guids": [],
                    "bases": { "pc-fixe": 1764000600, "portable1": 1764100500 }
                },
                {
                    "guid": "Player-1-A", "name": "Alt", "class": "MAGE", "race": "Troll", "level": 12,
                    "counting_since": null, "counters": { "quests": 4 }, "journal": {}, "events": [], "mobs": {},
                    "pvp": {}, "played": null, "previous_guids": [], "bases": { "pc-fixe": 1764000600 }
                }
            ]
        }))
        .unwrap()
    }

    fn character<'a>(db: &'a Table, guid: &str) -> &'a Table {
        db.get_table("characters").unwrap().get_table(guid).unwrap()
    }

    #[test]
    fn completes_an_existing_file_without_touching_local_state() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("WoWForeverGuilde.lua");
        std::fs::write(&path, EXISTING).unwrap();
        let done = complete_file(&path, &state(), 1764200001).unwrap();
        assert_eq!(
            done,
            Completion {
                characters: 2,
                created: false
            }
        );
        let text = std::fs::read_to_string(&path).unwrap();
        let parsed = parse_file(&text).unwrap();
        let Value::Table(db) = &parsed[0].1 else {
            panic!()
        };
        assert_eq!(db.get_str("installId"), Some("portable1")); // réglages et identifiant intacts
        assert_eq!(
            db.get_table("settings").unwrap().get("sharePlaytime"),
            Some(&Value::Bool(true))
        );
        let thrall = character(db, "Player-1-T");
        let counters = thrall.get_table("counters").unwrap();
        assert_eq!(counters.get_num("deaths"), Some(16.0));
        assert_eq!(
            counters.get_table("gathering").unwrap().get_num("mining"),
            Some(325.0)
        );
        assert_eq!(thrall.get_num("counting_since"), Some(1764000000.0)); // la plus ancienne
        assert_eq!(thrall.get_str("surname"), Some("Fils-de-Durotan")); // complété
        assert_eq!(
            thrall
                .get_table("gear")
                .unwrap()
                .get_table("head")
                .unwrap()
                .get_num("id"),
            Some(16842.0)
        );
        assert!(thrall
            .get_table("professions")
            .unwrap()
            .get_table("171")
            .is_some());
        let pvp = thrall.get_table("pvp").unwrap();
        assert_eq!(pvp.get_num("hk_lifetime"), Some(2340.0));
        assert_eq!(pvp.get_num("rank"), Some(3.0)); // état local conservé
        assert_eq!(
            pvp.get_table("bg")
                .unwrap()
                .get_table("Goulet")
                .unwrap()
                .get_num("played"),
            Some(13.0)
        );
        assert_eq!(thrall.get_num("played"), Some(123456.0));
        let seed = thrall.get_table("seed").unwrap();
        assert_eq!(seed.get_num("at"), Some(1764200000.0));
        let bases = seed.get_table("bases").unwrap();
        assert_eq!(bases.get_num("pc-fixe"), Some(1764000600.0));
        assert_eq!(bases.get_num("portable1"), Some(1764100500.0));
        let events = thrall.get_table("events").unwrap();
        assert_eq!(events.entries.len(), 1);
        // Personnage inconnu de ce PC : entrée créée avec son identité, prête pour l'addon.
        let alt = character(db, "Player-1-A");
        assert_eq!(alt.get_str("name"), Some("Alt"));
        assert_eq!(alt.get_str("class"), Some("MAGE"));
        assert_eq!(alt.get_num("level"), Some(12.0));
        assert_eq!(alt.get_num("created_at"), Some(1764200001.0));
        assert!(alt.get("counting_since").is_none());
        assert_eq!(
            alt.get_table("counters").unwrap().get_num("quests"),
            Some(4.0)
        );
        assert!(alt.get_table("journal").unwrap().entries.is_empty());
        assert!(!text.contains(".tmp"));
    }

    #[test]
    fn creates_the_file_on_a_fresh_pc() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp
            .path()
            .join("WTF/Account/WOW1/SavedVariables/WoWForeverGuilde.lua");
        let done = complete_file(&path, &state(), 1).unwrap();
        assert!(done.created && done.characters == 2);
        let text = std::fs::read_to_string(&path).unwrap();
        assert!(text.starts_with("WoWForeverGuildeDB = {\n"));
        let parsed = parse_file(&text).unwrap();
        let Value::Table(db) = &parsed[0].1 else {
            panic!()
        };
        assert!(db.get("installId").is_none()); // l'addon en tirera un au premier chargement
        assert_eq!(
            character(db, "Player-1-T")
                .get_table("counters")
                .unwrap()
                .get_num("kills"),
            Some(125.0)
        );
    }

    #[test]
    fn unreadable_file_is_left_alone() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("WoWForeverGuilde.lua");
        std::fs::write(&path, "WoWForeverGuildeDB = { [\"x\" = }").unwrap();
        assert!(matches!(
            complete_file(&path, &state(), 1),
            Err(CoreError::Parse(_))
        ));
        assert_eq!(
            std::fs::read_to_string(&path).unwrap(),
            "WoWForeverGuildeDB = { [\"x\" = }"
        );
    }
}
