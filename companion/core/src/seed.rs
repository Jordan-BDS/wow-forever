//! Complétion de l'addon depuis le site : l'état fusionné de chaque personnage (toutes installations) est
//! recopié dans `SavedVariables`, jeu fermé, avec une marque `seed` qui dit ce que ce fichier contient déjà
//! des autres installations (le site ne compte ensuite de celles-ci que ce qu'elles font après).

use std::fs;
use std::path::Path;

use crate::api::{SiteState, StateCharacter, StateWanted};
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

/// La clé du tableau pour cet ennemi : la sienne, ou celle du même ennemi sous une autre forme (l'addon lit
/// prénom et nom depuis la 0.6.12, le prénom seul avant). Connu par son prénom, il prend son nom complet ;
/// nommé par son prénom, c'est le seul du tableau qui le porte.
fn wanted_key(table: &mut Table, key: String, name: &str) -> String {
    if table.get(&key).is_some() {
        return key;
    }
    let first = key.split(' ').next().unwrap_or("").to_string();
    if key.contains(' ') {
        if let Some(Value::Table(mut short)) = table.get(&first).cloned() {
            short.set("name", Value::Str(name.to_string()));
            table.remove(&first);
            table.set(&key, Value::Table(short));
        }
        return key;
    }
    let mut same = table.entries.iter().filter_map(|(k, _)| match k {
        Key::Str(k) if k.split(' ').next() == Some(first.as_str()) => Some(k.clone()),
        _ => None,
    });
    match (same.next(), same.next()) {
        (Some(only), None) => only,
        _ => key,
    }
}

/// Le tableau Wanted de la guilde : le maximum de chaque valeur entre ce fichier et le site, la dernière position
/// la plus récente (« vu pour la dernière fois ») ; rien n'est retiré, les victimes et heures de kill locales restent.
/// La prime suit le dernier encaissement (`cashed`, heure du dernier kill) : celui du site plus récent que celui
/// du fichier, la prime du site remplace ; plus ancien, celle du fichier reste (le site est en retard).
fn complete_wanted(db: &mut Table, wanted: &[StateWanted], now: i64) {
    if wanted.is_empty() {
        return;
    }
    let table = db.table_mut("wanted");
    for enemy in wanted {
        let key = enemy
            .name
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
            .to_lowercase();
        if key.is_empty() {
            continue;
        }
        let key = wanted_key(table, key, &enemy.name);
        let entry = table.table_mut(&key);
        if entry.get("name").is_none() {
            entry.set("name", Value::Str(enemy.name.clone()));
        }
        if entry.get("class").is_none() {
            if let Some(class) = enemy.class.as_deref().filter(|c| !c.is_empty()) {
                entry.set("class", Value::Str(class.to_string()));
            }
        }
        let local = entry.get_num("points").unwrap_or(0.0);
        let local_cashed = entry.get_num("cashed").unwrap_or(0.0);
        let cashed = enemy.cashed.unwrap_or(0) as f64;
        let points = if cashed > local_cashed {
            entry.set("cashed", Value::Num(cashed));
            enemy.points as f64
        } else if cashed == local_cashed {
            local.max(enemy.points as f64)
        } else {
            local
        };
        entry.set("points", Value::Num(points));
        let kills = entry.get_num("kills").unwrap_or(0.0).max(enemy.kills as f64);
        entry.set("kills", Value::Num(kills));
        if entry.get("first").is_none() {
            entry.set("first", Value::Num(enemy.last_t.unwrap_or(now) as f64));
        }
        for list in ["victims", "kill_times"] {
            if entry.get(list).is_none() {
                entry.set(list, Value::Table(Table::default()));
            }
        }
        if let Some(t) = enemy.last_t {
            let local = entry
                .get_table("last")
                .and_then(|last| last.get_num("t"))
                .unwrap_or(0.0);
            if t as f64 > local {
                let mut last = Table::default();
                last.set("kind", Value::Str("seen".into()));
                last.set("t", Value::Num(t as f64));
                if let Some(map) = enemy.map {
                    last.set("map", Value::Num(map as f64));
                }
                if let (Some(x), Some(y)) = (enemy.x, enemy.y) {
                    last.set("x", Value::Num(x));
                    last.set("y", Value::Num(y));
                }
                last.set("zone", Value::Str(String::new()));
                last.set("sub", Value::Str(String::new()));
                entry.set("last", Value::Table(last));
            }
        }
    }
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
    complete_wanted(db, &state.wanted, now);
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
    fn completes_the_wanted_board_keeping_local_maxima() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("WoWForeverGuilde.lua");
        let existing = EXISTING.replace(
            "\t[\"characters\"] = {",
            "\t[\"wanted\"] = {\n\t\t[\"garrosh hurlenfer\"] = {\n\t\t\t[\"name\"] = \"Garrosh Hurlenfer\",\n\t\t\t[\"points\"] = 5,\n\t\t\t[\"kills\"] = 0,\n\t\t\t[\"last\"] = {\n\t\t\t\t[\"t\"] = 1764000000,\n\t\t\t},\n\t\t},\n\t},\n\t[\"characters\"] = {",
        );
        assert_ne!(existing, EXISTING);
        std::fs::write(&path, existing).unwrap();
        let mut state = state();
        state.wanted = serde_json::from_value(serde_json::json!([
            { "name": "Garrosh Hurlenfer", "class": "WARRIOR", "points": 3, "kills": 2, "last_t": 1764000700, "map": 1411, "x": 0.4, "y": 0.6 },
            { "name": "Vol'jin", "class": "SHAMAN", "points": 1, "kills": 0, "last_t": null, "map": null, "x": null, "y": null }
        ]))
        .unwrap();
        complete_file(&path, &state, 1764200001).unwrap();
        let text = std::fs::read_to_string(&path).unwrap();
        let assignments = parse_file(&text).unwrap();
        let Value::Table(db) = &assignments.iter().find(|(n, _)| n == DB_NAME).unwrap().1 else {
            panic!("pas une table");
        };
        let wanted = db.get_table("wanted").unwrap();
        let garrosh = wanted.get_table("garrosh hurlenfer").unwrap();
        assert_eq!(garrosh.get_num("points"), Some(5.0)); // le maximum des deux : la prime locale était plus haute
        assert_eq!(garrosh.get_num("kills"), Some(2.0));
        assert_eq!(garrosh.get_str("class"), Some("WARRIOR"));
        let last = garrosh.get_table("last").unwrap();
        assert_eq!(
            (last.get_num("t"), last.get_num("map"), last.get_str("kind")),
            (Some(1764000700.0), Some(1411.0), Some("seen"))
        );
        let voljin = wanted.get_table("vol'jin").unwrap();
        assert_eq!((voljin.get_num("points"), voljin.get_str("name")), (Some(1.0), Some("Vol'jin")));
        assert!(voljin.get("last").is_none() && voljin.get_table("victims").is_some());
    }

    #[test]
    fn a_cashed_bounty_follows_the_latest_kill() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("WoWForeverGuilde.lua");
        let existing = EXISTING.replace(
            "\t[\"characters\"] = {",
            "\t[\"wanted\"] = {\n\t\t[\"garrosh hurlenfer\"] = {\n\t\t\t[\"name\"] = \"Garrosh Hurlenfer\",\n\t\t\t[\"points\"] = 5,\n\t\t\t[\"kills\"] = 0,\n\t\t},\n\t\t[\"vol'jin\"] = {\n\t\t\t[\"name\"] = \"Vol'jin\",\n\t\t\t[\"points\"] = 0,\n\t\t\t[\"kills\"] = 1,\n\t\t\t[\"cashed\"] = 1764000900,\n\t\t},\n\t},\n\t[\"characters\"] = {",
        );
        assert_ne!(existing, EXISTING);
        std::fs::write(&path, existing).unwrap();
        let mut state = state();
        // Garrosh abattu depuis (le site le sait, pas ce fichier) ; pour Vol'jin, c'est le site qui est en retard.
        state.wanted = serde_json::from_value(serde_json::json!([
            { "name": "Garrosh Hurlenfer", "class": "WARRIOR", "points": 1, "kills": 1, "cashed": 1764000700, "last_t": 1764000800 },
            { "name": "Vol'jin Sombrelance", "class": "SHAMAN", "points": 4, "kills": 0, "cashed": null, "last_t": 1764000100 },
            // Connu du fichier par son nom complet, du site par son prénom seul : le même ennemi.
            { "name": "Garrosh", "class": "WARRIOR", "points": 0, "kills": 1, "cashed": 1764000600, "last_t": 1764000600 }
        ]))
        .unwrap();
        complete_file(&path, &state, 1764200001).unwrap();
        let text = std::fs::read_to_string(&path).unwrap();
        let assignments = parse_file(&text).unwrap();
        let Value::Table(db) = &assignments.iter().find(|(n, _)| n == DB_NAME).unwrap().1 else {
            panic!("pas une table");
        };
        let wanted = db.get_table("wanted").unwrap();
        let garrosh = wanted.get_table("garrosh hurlenfer").unwrap();
        assert_eq!(
            (
                garrosh.get_num("points"),
                garrosh.get_num("cashed"),
                garrosh.get_num("kills")
            ),
            (Some(1.0), Some(1764000700.0), Some(1.0))
        );
        // Vol'jin, connu par son prénom, prend le nom complet que donne le site ; pas de doublon.
        assert!(wanted.get("vol'jin").is_none() && wanted.get("garrosh").is_none());
        let voljin = wanted.get_table("vol'jin sombrelance").unwrap();
        assert_eq!(voljin.get_str("name"), Some("Vol'jin Sombrelance"));
        assert_eq!(
            (voljin.get_num("points"), voljin.get_num("cashed")),
            (Some(0.0), Some(1764000900.0))
        );
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
