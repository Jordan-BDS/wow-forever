//! Le fichier `SavedVariables` de l'addon : on n'interprète pas le Lua, on extrait la chaîne `export = "WFG…"`.

use std::fs;
use std::path::{Path, PathBuf};

use regex::Regex;
use sha2::{Digest, Sha256};

pub const ADDON_NAME: &str = "WoWForeverGuilde";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SavedVarsFile {
    /// Nom du compte WoW (dossier sous `WTF/Account/`).
    pub account: String,
    pub path: PathBuf,
}

/// Tous les fichiers `WTF/Account/<compte>/SavedVariables/WoWForeverGuilde.lua` d'une installation.
pub fn find_saved_variables(game_dir: &Path) -> Vec<SavedVarsFile> {
    let accounts = crate::wowdir::wtf_accounts_dir(game_dir);
    let mut found = Vec::new();
    let Ok(entries) = fs::read_dir(&accounts) else {
        return found;
    };
    for entry in entries.flatten() {
        let account = entry.file_name().to_string_lossy().to_string();
        if account.eq_ignore_ascii_case("SavedVariables") {
            continue; // le dossier au niveau du compte Battle.net, pas un compte WoW
        }
        let path = entry
            .path()
            .join("SavedVariables")
            .join(format!("{ADDON_NAME}.lua"));
        if path.is_file() {
            found.push(SavedVarsFile { account, path });
        }
    }
    found.sort_by(|a, b| a.account.cmp(&b.account));
    found
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportCode {
    pub code: String,
    /// Horodatage (secondes) écrit par l'addon à côté du code, si présent.
    pub exported_at: Option<i64>,
}

/// Extrait le code d'export tel que l'addon l'a écrit (`["export"] = "WFG1:…"`), sans interpréter le Lua.
pub fn extract_export(lua: &str) -> Option<ExportCode> {
    let code_re =
        Regex::new(r#"\["export"\]\s*=\s*"(WFG\d+:[0-9a-f]{8}:[A-Za-z0-9+/=]+)""#).unwrap();
    let at_re = Regex::new(r#"\["export_at"\]\s*=\s*(\d+)"#).unwrap();
    let code = code_re.captures(lua)?.get(1)?.as_str().to_string();
    let exported_at = at_re
        .captures(lua)
        .and_then(|c| c.get(1))
        .and_then(|m| m.as_str().parse().ok());
    Some(ExportCode { code, exported_at })
}

pub fn read_export(path: &Path) -> std::io::Result<Option<ExportCode>> {
    let text = fs::read_to_string(path)?;
    Ok(extract_export(&text))
}

/// Empreinte d'un code, pour ne pas renvoyer deux fois la même chose.
pub fn fingerprint(code: &str) -> String {
    let compact: String = code.split_whitespace().collect();
    hex::encode(Sha256::digest(compact.as_bytes()))
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"
WoWForeverGuildeDB = {
	["version"] = 1,
	["installId"] = "k2j3h4g5",
	["export_at"] = 1764000000,
	["export"] = "WFG1:2d0c5a5d:PY5BT8MwDIX/i8/plHSjhdwmjYnLGBLcEEJW4tFqaVI56QSa+t9xxcTN/vz83rsCep8iWNArs9Kg==",
	["characters"] = {
		["Player-1-000ABC01"] = {
			["name"] = "Thrall",
		},
	},
}
"#;

    #[test]
    fn extracts_code_and_timestamp() {
        let export = extract_export(SAMPLE).unwrap();
        assert!(export.code.starts_with("WFG1:2d0c5a5d:"));
        assert_eq!(export.exported_at, Some(1764000000));
        assert!(extract_export("WoWForeverGuildeDB = {}").is_none());
    }

    #[test]
    fn finds_files_per_wow_account() {
        let tmp = tempfile::tempdir().unwrap();
        let game = tmp.path();
        for account in ["WOW2", "WOW1", "SavedVariables"] {
            let dir = game
                .join("WTF/Account")
                .join(account)
                .join("SavedVariables");
            std::fs::create_dir_all(&dir).unwrap();
            std::fs::write(dir.join("WoWForeverGuilde.lua"), SAMPLE).unwrap();
        }
        let files = find_saved_variables(game);
        assert_eq!(
            files.iter().map(|f| f.account.as_str()).collect::<Vec<_>>(),
            ["WOW1", "WOW2"]
        );
        assert_eq!(
            read_export(&files[0].path).unwrap().unwrap().exported_at,
            Some(1764000000)
        );
    }

    #[test]
    fn fingerprint_ignores_whitespace() {
        assert_eq!(fingerprint("WFG1:ab\ncd"), fingerprint("WFG1:abcd"));
        assert_eq!(fingerprint("x").len(), 64);
    }
}
