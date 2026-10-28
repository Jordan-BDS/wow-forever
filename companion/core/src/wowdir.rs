//! Dossier du jeu : détection des installations habituelles, validation, normalisation.

use std::path::{Path, PathBuf};

/// Nom du sous-dossier de version de WoW Forever (comme `_classic_era_` ou `_retail_`).
pub const FOREVER_DIR: &str = "_forever_";

/// Le dossier passé est-il un dossier de version WoW (celui qui contient `Interface/` et `WTF/`) ?
pub fn is_game_dir(path: &Path) -> bool {
    if !path.is_dir() {
        return false;
    }
    let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
    let versioned = name.len() > 2 && name.starts_with('_') && name.ends_with('_');
    let has_client = [
        "Wow.exe",
        "WowClassic.exe",
        "World of Warcraft.app",
        "World of Warcraft Classic.app",
    ]
    .iter()
    .any(|exe| path.join(exe).exists());
    versioned || has_client || (path.join("Interface").is_dir() && path.join("WTF").is_dir())
}

/// Accepte le dossier choisi par le joueur : s'il a désigné `World of Warcraft/`, on descend dans `_forever_/`.
pub fn normalize(chosen: &Path) -> Option<PathBuf> {
    if is_game_dir(chosen) {
        return Some(chosen.to_path_buf());
    }
    let forever = chosen.join(FOREVER_DIR);
    if is_game_dir(&forever) {
        return Some(forever);
    }
    None
}

/// Emplacements habituels, filtrés sur ceux qui existent.
pub fn candidates() -> Vec<PathBuf> {
    let mut roots: Vec<PathBuf> = Vec::new();
    for var in ["PROGRAMFILES(X86)", "PROGRAMFILES", "ProgramW6432"] {
        if let Ok(v) = std::env::var(var) {
            roots.push(PathBuf::from(v).join("World of Warcraft"));
        }
    }
    for drive in ["C", "D", "E"] {
        roots.push(PathBuf::from(format!(
            "{drive}:\\Program Files (x86)\\World of Warcraft"
        )));
        roots.push(PathBuf::from(format!(
            "{drive}:\\Program Files\\World of Warcraft"
        )));
        roots.push(PathBuf::from(format!("{drive}:\\World of Warcraft")));
        roots.push(PathBuf::from(format!("{drive}:\\Games\\World of Warcraft")));
    }
    roots.push(PathBuf::from("/Applications/World of Warcraft"));
    if let Some(home) = dirs::home_dir() {
        roots.push(
            home.join("Games/world-of-warcraft/drive_c/Program Files (x86)/World of Warcraft"),
        );
        roots.push(home.join(".wine/drive_c/Program Files (x86)/World of Warcraft"));
    }
    let mut found: Vec<PathBuf> = roots
        .into_iter()
        .filter_map(|root| normalize(&root))
        .collect();
    found.dedup();
    found
}

pub fn addons_dir(game_dir: &Path) -> PathBuf {
    game_dir.join("Interface").join("AddOns")
}

pub fn wtf_accounts_dir(game_dir: &Path) -> PathBuf {
    game_dir.join("WTF").join("Account")
}

pub fn chat_log_path(game_dir: &Path) -> PathBuf {
    game_dir.join("Logs").join("WoWChatLog.txt")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn normalize_descends_into_forever() {
        let tmp = tempfile::tempdir().unwrap();
        let wow = tmp.path().join("World of Warcraft");
        fs::create_dir_all(wow.join(FOREVER_DIR).join("Interface")).unwrap();
        assert_eq!(normalize(&wow).unwrap(), wow.join(FOREVER_DIR));
        assert_eq!(
            normalize(&wow.join(FOREVER_DIR)).unwrap(),
            wow.join(FOREVER_DIR)
        );
        assert!(normalize(tmp.path()).is_none());
    }

    #[test]
    fn game_dir_detected_by_client_or_folders() {
        let tmp = tempfile::tempdir().unwrap();
        let plain = tmp.path().join("plain");
        fs::create_dir_all(plain.join("Interface")).unwrap();
        fs::create_dir_all(plain.join("WTF")).unwrap();
        assert!(is_game_dir(&plain));
        let exe = tmp.path().join("exe");
        fs::create_dir_all(&exe).unwrap();
        fs::write(exe.join("Wow.exe"), b"").unwrap();
        assert!(is_game_dir(&exe));
        assert!(!is_game_dir(&tmp.path().join("nope")));
    }
}
