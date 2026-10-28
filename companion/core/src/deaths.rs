//! Annonces de mort : lecture des lignes balisées par l'addon dans le journal de chat (`Logs/WoWChatLog.txt`).
//! Le compagnon ne retient **que** ces lignes ; tout le reste du chat est ignoré sans être conservé.

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use serde::Serialize;

pub const DEATH_PREFIX: &str = "WFG\tDEATH\t1\t";

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DeathEvent {
    pub guid: String,
    pub name: String,
    pub surname: String,
    pub class: String,
    pub level: u32,
    pub killer: String,
    pub zone: String,
    pub subzone: String,
    pub timestamp: i64,
}

/// Une ligne du journal de chat → événement de mort, ou None pour toute autre ligne.
pub fn parse_line(line: &str) -> Option<DeathEvent> {
    let start = line.find(DEATH_PREFIX)?;
    let payload = &line[start + DEATH_PREFIX.len()..];
    let fields: Vec<&str> = payload.trim_end_matches(['\r', '\n']).split('\t').collect();
    if fields.len() < 9 {
        return None;
    }
    Some(DeathEvent {
        guid: fields[0].to_string(),
        name: fields[1].to_string(),
        surname: fields[2].to_string(),
        class: fields[3].to_string(),
        level: fields[4].parse().ok()?,
        killer: fields[5].to_string(),
        zone: fields[6].to_string(),
        subzone: fields[7].to_string(),
        timestamp: fields[8].parse().ok()?,
    })
}

/// Lecture incrémentale du journal de chat : on repart de l'offset mémorisé, jamais du début.
pub struct ChatLogTail {
    path: PathBuf,
    offset: u64,
    partial: String,
}

impl ChatLogTail {
    /// `start_at_end` : à l'ouverture, on ignore ce qui est déjà écrit (pas d'annonces de morts passées).
    pub fn new(path: &Path, start_at_end: bool) -> Self {
        let offset = if start_at_end {
            std::fs::metadata(path).map(|m| m.len()).unwrap_or(0)
        } else {
            0
        };
        Self {
            path: path.to_path_buf(),
            offset,
            partial: String::new(),
        }
    }

    /// Nouvelles morts depuis le dernier appel. Un fichier tronqué (vidé par le compagnon) repart de zéro.
    pub fn poll(&mut self) -> std::io::Result<Vec<DeathEvent>> {
        let mut file = match File::open(&self.path) {
            Ok(f) => f,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(e) => return Err(e),
        };
        let len = file.metadata()?.len();
        if len < self.offset {
            self.offset = 0;
            self.partial.clear();
        }
        file.seek(SeekFrom::Start(self.offset))?;
        let mut buf = Vec::new();
        file.read_to_end(&mut buf)?;
        self.offset = len;
        let text = self.partial.clone() + &String::from_utf8_lossy(&buf);
        let mut lines: Vec<&str> = text.split('\n').collect();
        self.partial = if text.ends_with('\n') {
            String::new()
        } else {
            lines.pop().unwrap_or("").to_string()
        };
        Ok(lines.iter().filter_map(|l| parse_line(l)).collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    const LINE: &str = "10/28 21:14:03.123  [5. wfgdeaths] [Thrall]: WFG\tDEATH\t1\tPlayer-1-000ABC01\tThrall\tFils-de-Durotan\tChaman\t60\tSanglier des Tarides\tLes Tarides\t\t1764000000";

    #[test]
    fn parses_only_addon_lines() {
        let death = parse_line(LINE).unwrap();
        assert_eq!(
            (death.name.as_str(), death.level, death.killer.as_str()),
            ("Thrall", 60, "Sanglier des Tarides")
        );
        assert_eq!(death.subzone, "");
        assert!(parse_line("10/28 21:14:03.123  [Guild] [Garona]: on raid ce soir ?").is_none());
        assert!(parse_line("WFG\tDEATH\t1\tincomplet").is_none());
    }

    #[test]
    fn tail_reads_only_new_lines_and_survives_truncation() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("WoWChatLog.txt");
        std::fs::write(&path, format!("{LINE}\n")).unwrap();
        let mut tail = ChatLogTail::new(&path, true);
        assert!(tail.poll().unwrap().is_empty()); // l'ancienne mort n'est pas annoncée
        let mut f = std::fs::OpenOptions::new()
            .append(true)
            .open(&path)
            .unwrap();
        write!(
            f,
            "10/28 21:20:00.000  [Guild] [X]: gg\n{}",
            LINE.replace("Thrall", "Garona")
        )
        .unwrap();
        assert!(tail.poll().unwrap().is_empty()); // ligne incomplète : on attend la fin
        writeln!(f).unwrap();
        let deaths = tail.poll().unwrap();
        assert_eq!(deaths.len(), 1);
        assert_eq!(deaths[0].name, "Garona");
        std::fs::write(&path, format!("{LINE}\n")).unwrap(); // vidé puis réécrit
        assert_eq!(tail.poll().unwrap().len(), 1);
    }
}
