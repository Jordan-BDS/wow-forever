//! L'addon est embarqué dans l'exécutable à la compilation : une seule version pour les deux.
//! Le compagnon le copie dans `Interface/AddOns/` quand la version installée diffère.

use std::fs;
use std::path::Path;

use include_dir::{include_dir, Dir, DirEntry};
use regex::Regex;

use crate::error::Result;
use crate::savedvars::ADDON_NAME;

static ADDON: Dir<'_> = include_dir!("$CARGO_MANIFEST_DIR/../../addon/WoWForeverGuilde");

fn version_from_toc(toc: &str) -> Option<String> {
    let re = Regex::new(r"(?m)^## Version:\s*(.+?)\s*$").unwrap();
    re.captures(toc).map(|c| c[1].to_string())
}

/// Version de l'addon livrée avec cet exécutable.
pub fn embedded_version() -> String {
    ADDON
        .get_file(format!("{ADDON_NAME}.toc"))
        .and_then(|f| f.contents_utf8())
        .and_then(version_from_toc)
        .unwrap_or_else(|| "0.0.0".to_string())
}

/// Version installée dans le dossier du jeu, s'il y en a une.
pub fn installed_version(addons_dir: &Path) -> Option<String> {
    let toc = addons_dir
        .join(ADDON_NAME)
        .join(format!("{ADDON_NAME}.toc"));
    fs::read_to_string(toc)
        .ok()
        .and_then(|t| version_from_toc(&t))
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InstallOutcome {
    Installed { version: String },
    Updated { from: String, to: String },
    UpToDate { version: String },
}

fn collect_files<'a>(dir: &'a Dir<'a>, out: &mut Vec<&'a include_dir::File<'a>>) {
    for entry in dir.entries() {
        match entry {
            DirEntry::File(f) => out.push(f),
            DirEntry::Dir(d) => collect_files(d, out),
        }
    }
}

/// Copie l'addon embarqué dans `Interface/AddOns/WoWForeverGuilde/` (fichiers en trop supprimés).
/// `force` réécrit même si la version est identique.
pub fn install(addons_dir: &Path, force: bool) -> Result<InstallOutcome> {
    let embedded = embedded_version();
    let installed = installed_version(addons_dir);
    if !force && installed.as_deref() == Some(embedded.as_str()) {
        return Ok(InstallOutcome::UpToDate { version: embedded });
    }
    let target = addons_dir.join(ADDON_NAME);
    if target.exists() {
        fs::remove_dir_all(&target)?;
    }
    let mut files = Vec::new();
    collect_files(&ADDON, &mut files);
    for file in files {
        let dest = target.join(file.path());
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&dest, file.contents())?;
    }
    Ok(match installed {
        Some(from) => InstallOutcome::Updated { from, to: embedded },
        None => InstallOutcome::Installed { version: embedded },
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_addon_has_a_version_and_its_files() {
        let version = embedded_version();
        assert!(
            version.chars().next().unwrap().is_ascii_digit(),
            "{version}"
        );
        assert!(ADDON.get_file("Core.lua").is_some());
        assert!(ADDON.get_file("Collectors/Deaths.lua").is_some());
        assert!(ADDON.get_file("Libs/LibDeflate/LibDeflate.lua").is_some());
    }

    #[test]
    fn install_then_update_then_up_to_date() {
        let tmp = tempfile::tempdir().unwrap();
        let addons = tmp.path().join("Interface/AddOns");
        let outcome = install(&addons, false).unwrap();
        assert!(matches!(outcome, InstallOutcome::Installed { .. }));
        assert!(addons.join("WoWForeverGuilde/Collectors/PvE.lua").is_file());
        assert_eq!(installed_version(&addons).unwrap(), embedded_version());
        // Un fichier parasite et une vieille version : on remplace tout.
        fs::write(addons.join("WoWForeverGuilde/Vieux.lua"), "-- obsolete").unwrap();
        let toc = addons.join("WoWForeverGuilde/WoWForeverGuilde.toc");
        let old = fs::read_to_string(&toc)
            .unwrap()
            .replace(&embedded_version(), "0.0.1");
        fs::write(&toc, old).unwrap();
        let outcome = install(&addons, false).unwrap();
        assert_eq!(
            outcome,
            InstallOutcome::Updated {
                from: "0.0.1".into(),
                to: embedded_version()
            }
        );
        assert!(!addons.join("WoWForeverGuilde/Vieux.lua").exists());
        assert!(matches!(
            install(&addons, false).unwrap(),
            InstallOutcome::UpToDate { .. }
        ));
    }
}
