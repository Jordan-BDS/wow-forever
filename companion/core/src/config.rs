//! Réglages du compagnon et jeton, dans le dossier de configuration de l'utilisateur
//! (`%APPDATA%\WoWForeverGuilde` sous Windows, `~/Library/Application Support/…` sous macOS).
//! Le coffre système (Credential Manager / Keychain) viendra dans l'application, pas dans ce cœur.

use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::error::{CoreError, Result};

pub const APP_DIR: &str = "WoWForeverGuilde";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct Config {
    pub site_url: String,
    pub game_dir: Option<PathBuf>,
    pub device_name: String,
    pub token: Option<String>,
    pub display_name: Option<String>,
    pub autostart: bool,
    /// Empreinte du dernier code envoyé, par compte WoW.
    pub last_fingerprints: std::collections::BTreeMap<String, String>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            site_url: "https://wow.koj.dev".to_string(),
            game_dir: None,
            device_name: hostname(),
            token: None,
            display_name: None,
            autostart: true,
            last_fingerprints: Default::default(),
        }
    }
}

fn hostname() -> String {
    std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .ok()
        .filter(|h| !h.is_empty())
        .unwrap_or_else(|| "Mon PC".to_string())
}

pub fn default_dir() -> Result<PathBuf> {
    dirs::config_dir()
        .map(|d| d.join(APP_DIR))
        .ok_or_else(|| CoreError::Config("dossier de configuration introuvable".into()))
}

impl Config {
    pub fn path_in(dir: &Path) -> PathBuf {
        dir.join("config.json")
    }

    pub fn load_from(dir: &Path) -> Result<Self> {
        let path = Self::path_in(dir);
        match fs::read_to_string(&path) {
            Ok(text) => serde_json::from_str(&text)
                .map_err(|e| CoreError::Config(format!("config illisible : {e}"))),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Self::default()),
            Err(e) => Err(e.into()),
        }
    }

    pub fn save_to(&self, dir: &Path) -> Result<()> {
        fs::create_dir_all(dir)?;
        let path = Self::path_in(dir);
        let tmp = path.with_extension("json.tmp");
        fs::write(
            &tmp,
            serde_json::to_string_pretty(self).expect("config sérialisable"),
        )?;
        fs::rename(&tmp, &path)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = fs::set_permissions(&path, fs::Permissions::from_mode(0o600));
        }
        Ok(())
    }

    pub fn is_paired(&self) -> bool {
        self.token.is_some()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_and_defaults() {
        let tmp = tempfile::tempdir().unwrap();
        let mut config = Config::load_from(tmp.path()).unwrap();
        assert!(!config.is_paired() && config.autostart);
        config.token = Some("tok".into());
        config.last_fingerprints.insert("WOW1".into(), "abc".into());
        config.save_to(tmp.path()).unwrap();
        let again = Config::load_from(tmp.path()).unwrap();
        assert_eq!(again, config);
        // Un champ inconnu ou manquant ne casse pas la lecture.
        fs::write(
            Config::path_in(tmp.path()),
            r#"{"site_url": "https://x", "future": 1}"#,
        )
        .unwrap();
        assert_eq!(Config::load_from(tmp.path()).unwrap().site_url, "https://x");
    }
}
