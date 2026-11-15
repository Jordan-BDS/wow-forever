//! Prix de l'hôtel des ventes : l'addon NaowhForever garde le dernier scan complet dans son `SavedVariables`
//! (`ahPrices`, par hôtel : `prices`, `listed`, `time`). Le compagnon de qui en a le droit sur le site (tout membre)
//! envoie chaque nouveau scan ; chez les autres, rien n'est lu ni envoyé. Notre addon n'y est pour rien.
//!
//! Auctionator est lu de la même façon (`AUCTIONATOR_PRICE_DATABASE`, par royaume : une chaîne CBOR écrite par
//! le client). Sa base ne date pas ses scans à la seconde, seulement au jour : le scan envoyé est le dernier jour
//! où une bonne part de la base a été vue (un scan complet, pas une recherche), daté de l'écriture du fichier.
//! Il repart dès que les prix de ce jour ont changé (un second scan le même jour ; avant la 0.7.11, un seul par
//! jour). Elle compte des quantités, pas des enchères : le nombre d'enchères n'est pas envoyé.

use std::fs;
use std::path::{Path, PathBuf};

use regex::Regex;
use serde::Serialize;

use crate::api::SiteClient;
use crate::config::Config;
use crate::error::CoreError;

/// L'addon tiers dont on lit le scan (fichier `WTF/Account/<compte>/SavedVariables/NaowhForever.lua`).
pub const SCAN_ADDON: &str = "NaowhForever";

/// L'autre addon tiers lu (`SavedVariables/Auctionator.lua`).
pub const AUCTIONATOR: &str = "Auctionator";
/// Jour zéro des jours d'Auctionator : le 1er janvier 2020 (UTC ; l'addon compte en heure locale).
const AUCTIONATOR_DAY_0: i64 = 1_577_836_800;
/// Un jour compte pour un scan complet s'il a vu au moins ce nombre d'objets, et le tiers de la base.
const AUCTIONATOR_MIN_ITEMS: usize = 200;

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
    find_addon_files(game_dir, SCAN_ADDON)
}

/// Les fichiers `SavedVariables/<addon>.lua`, un par compte WoW de l'installation.
pub fn find_addon_files(game_dir: &Path, addon: &str) -> Vec<PathBuf> {
    let mut found = Vec::new();
    let Ok(entries) = fs::read_dir(crate::wowdir::wtf_accounts_dir(game_dir)) else {
        return found;
    };
    for entry in entries.flatten() {
        let path = entry
            .path()
            .join("SavedVariables")
            .join(format!("{addon}.lua"));
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

/// Le dernier scan complet qu'Auctionator garde d'un royaume.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuctionatorScan {
    /// Le royaume, tel qu'Auctionator l'écrit.
    pub house: String,
    /// Le jour du scan, compté par Auctionator depuis le 1er janvier 2020.
    pub day: i64,
    /// (objet, prix, rien), trié par objet.
    pub items: Vec<(u32, u64, Option<u32>)>,
}

/// Une valeur CBOR, réduite à ce que la base d'Auctionator contient.
enum Cbor {
    Int(u64),
    Text(Vec<u8>),
    Map(Vec<(Cbor, Cbor)>),
    Other,
}

struct CborReader<'a> {
    data: &'a [u8],
    pos: usize,
}

impl<'a> CborReader<'a> {
    fn take(&mut self, n: usize) -> Option<&'a [u8]> {
        let end = self.pos.checked_add(n)?;
        let slice = self.data.get(self.pos..end)?;
        self.pos = end;
        Some(slice)
    }

    /// (type majeur, information, valeur). Les longueurs indéfinies, que le client n'écrit pas : rien.
    fn head(&mut self) -> Option<(u8, u8, u64)> {
        let first = *self.data.get(self.pos)?;
        self.pos += 1;
        let (major, info) = (first >> 5, first & 31);
        let value = match info {
            0..=23 => u64::from(info),
            24..=27 => {
                let bytes = self.take(1usize << (info - 24))?;
                bytes.iter().fold(0u64, |acc, b| (acc << 8) | u64::from(*b))
            }
            _ => return None,
        };
        Some((major, info, value))
    }

    fn number(value: f64) -> Cbor {
        if value.is_finite() && value >= 0.0 {
            Cbor::Int(value.round() as u64)
        } else {
            Cbor::Other
        }
    }

    fn value(&mut self, depth: usize) -> Option<Cbor> {
        if depth > 16 {
            return None;
        }
        let (major, info, value) = self.head()?;
        Some(match major {
            0 => Cbor::Int(value),
            2 | 3 => Cbor::Text(self.take(usize::try_from(value).ok()?)?.to_vec()),
            4 => {
                // Une liste (la table vide `l`) : lue pour avancer, rien n'en est gardé.
                for _ in 0..value {
                    self.value(depth + 1)?;
                }
                Cbor::Other
            }
            5 => {
                let mut pairs = Vec::new();
                for _ in 0..value {
                    let key = self.value(depth + 1)?;
                    let item = self.value(depth + 1)?;
                    pairs.push((key, item));
                }
                Cbor::Map(pairs)
            }
            6 => self.value(depth + 1)?,
            7 if info == 26 => Self::number(f64::from(f32::from_bits(value as u32))),
            7 if info == 27 => Self::number(f64::from_bits(value)),
            _ => Cbor::Other,
        })
    }
}

/// Le contenu d'une chaîne Lua telle que le client l'écrit : `\\`, `\"`, `\n`, `\r` et `\ddd` (décimal) ; les
/// autres octets sont écrits tels quels.
fn lua_unescape(raw: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(raw.len());
    let mut i = 0;
    while i < raw.len() {
        let byte = raw[i];
        i += 1;
        if byte != b'\\' || i >= raw.len() {
            out.push(byte);
            continue;
        }
        let escaped = raw[i];
        if escaped.is_ascii_digit() {
            let mut code: u32 = 0;
            let mut digits = 0;
            while digits < 3 && i < raw.len() && raw[i].is_ascii_digit() {
                code = code * 10 + u32::from(raw[i] - b'0');
                i += 1;
                digits += 1;
            }
            out.push((code & 0xff) as u8);
            continue;
        }
        i += 1;
        out.push(match escaped {
            b'n' => b'\n',
            b'r' => b'\r',
            b't' => b'\t',
            b'a' => 7,
            b'b' => 8,
            b'f' => 12,
            b'v' => 11,
            other => other,
        });
    }
    out
}

/// Une clé d'Auctionator lue comme un nombre : l'objet (« 2589 ») ou le jour (« 2507 »), écrits en texte.
fn key_number(key: &Cbor) -> Option<u64> {
    match key {
        Cbor::Int(n) => Some(*n),
        Cbor::Text(text) => std::str::from_utf8(text).ok()?.parse().ok(),
        _ => None,
    }
}

fn field<'c>(pairs: &'c [(Cbor, Cbor)], name: &[u8]) -> Option<&'c Cbor> {
    pairs
        .iter()
        .find(|(key, _)| matches!(key, Cbor::Text(text) if text.as_slice() == name))
        .map(|(_, value)| value)
}

/// Ce qu'on a lu d'un royaume dans `Auctionator.lua` : son dernier scan complet, ou pourquoi il n'y en a pas.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuctionatorRealm {
    /// Le royaume, tel qu'Auctionator l'écrit.
    pub house: String,
    pub scan: Option<AuctionatorScan>,
    /// Sans scan : « unreadable » (base d'un autre format, coupée) ou « no_scan » (lisible, pas de scan complet).
    pub kind: &'static str,
    /// Ce qu'on a trouvé, en clair, pour le rapport envoyé au site.
    pub note: String,
}

/// Ce qu'on a lu de `Auctionator.lua`.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct AuctionatorFile {
    /// La base de prix (`AUCTIONATOR_PRICE_DATABASE`) est dans le fichier.
    pub found: bool,
    /// Sa version (`__dbversion`), si elle est écrite.
    pub version: Option<i64>,
    pub realms: Vec<AuctionatorRealm>,
}

fn unread(house: String, kind: &'static str, note: String) -> AuctionatorRealm {
    AuctionatorRealm {
        house,
        scan: None,
        kind,
        note,
    }
}

/// Lit `Auctionator.lua` : par royaume, le dernier scan complet ou la raison de son absence. Par objet, la base
/// garde le dernier prix vu (`m`) et les jours où il a été vu (`h`). Le scan : les objets vus pour la dernière
/// fois le jour le plus récent qui en compte assez (`AUCTIONATOR_MIN_ITEMS` et le tiers de la base) ; des
/// recherches à la main ne font pas un scan.
pub fn read_auctionator(lua: &[u8]) -> AuctionatorFile {
    const KEY_END: &[u8] = b"\"] = ";
    const VERSION: &[u8] = b"__dbversion\"] = ";
    let mut file = AuctionatorFile::default();
    for line in lua.split(|byte| *byte == b'\n') {
        let line = line.strip_suffix(b"\r").unwrap_or(line);
        if !file.found {
            file.found = line.starts_with(b"AUCTIONATOR_PRICE_DATABASE = {");
            continue;
        }
        if line.starts_with(b"}") {
            break;
        }
        // ["royaume"] = "…",
        let Some(rest) = line.strip_prefix(b"[\"") else {
            continue;
        };
        if let Some(number) = rest.strip_prefix(VERSION) {
            let digits: Vec<u8> = number
                .iter()
                .copied()
                .take_while(|byte| byte.is_ascii_digit())
                .collect();
            file.version = String::from_utf8_lossy(&digits).parse().ok();
            continue;
        }
        let Some(split) = rest
            .windows(KEY_END.len())
            .position(|window| window == KEY_END)
        else {
            continue;
        };
        let house = String::from_utf8_lossy(&rest[..split]).into_owned();
        let value = &rest[split + KEY_END.len()..];
        let Some(body) = value.strip_prefix(b"\"") else {
            let note = if value.starts_with(b"{") {
                "base écrite en table Lua et non en chaîne : format d'une autre version d'Auctionator, pas lu"
            } else {
                "valeur inattendue à la place de la base de prix"
            };
            file.realms.push(unread(house, "unreadable", note.to_string()));
            continue;
        };
        let body = body.strip_suffix(b",").unwrap_or(body);
        let Some(body) = body.strip_suffix(b"\"") else {
            file.realms.push(unread(
                house,
                "unreadable",
                "ligne de la base coupée (fichier en cours d'écriture ?)".to_string(),
            ));
            continue;
        };
        let data = lua_unescape(body);
        let mut reader = CborReader {
            data: &data,
            pos: 0,
        };
        let Some(Cbor::Map(entries)) = reader.value(0) else {
            let note = format!(
                "chaîne de {} octets illisible (pas du CBOR, premier octet {}) : autre format de base",
                data.len(),
                data.first().copied().unwrap_or(0)
            );
            file.realms.push(unread(house, "unreadable", note));
            continue;
        };
        // (objet, dernier jour vu, dernier prix)
        let mut rows: Vec<(u32, u64, u64)> = Vec::new();
        let mut per_day: std::collections::BTreeMap<u64, usize> = Default::default();
        for (key, value) in &entries {
            let Some(id) = key_number(key).and_then(|n| u32::try_from(n).ok()) else {
                continue;
            };
            let Cbor::Map(fields) = value else {
                continue;
            };
            let Some(Cbor::Int(price)) = field(fields, b"m") else {
                continue;
            };
            let Some(Cbor::Map(days)) = field(fields, b"h") else {
                continue;
            };
            let Some(last) = days.iter().filter_map(|(day, _)| key_number(day)).max() else {
                continue;
            };
            if id == 0 || *price == 0 {
                continue;
            }
            rows.push((id, last, *price));
            *per_day.entry(last).or_insert(0) += 1;
        }
        let total = rows.len();
        let Some(day) = per_day
            .iter()
            .rev()
            .find(|(_, count)| **count >= AUCTIONATOR_MIN_ITEMS && **count * 3 >= total)
            .map(|(day, _)| *day)
        else {
            let note = match per_day.iter().max_by_key(|(_, count)| **count) {
                Some((best, count)) => format!(
                    "pas de scan complet : {total} objets lisibles sur {} entrées, le jour le plus fourni ({best}) en compte {count} ; il en faut {AUCTIONATOR_MIN_ITEMS} et le tiers de la base",
                    entries.len()
                ),
                None => format!("aucun objet lisible sur {} entrées de la base", entries.len()),
            };
            file.realms.push(unread(house, "no_scan", note));
            continue;
        };
        let mut items: Vec<(u32, u64, Option<u32>)> = rows
            .iter()
            .filter(|row| row.1 == day)
            .map(|row| (row.0, row.2, None))
            .collect();
        items.sort();
        let note = format!(
            "{} objets vus le dernier jour de scan, sur {total} dans la base",
            items.len()
        );
        file.realms.push(AuctionatorRealm {
            house: house.clone(),
            scan: Some(AuctionatorScan {
                house,
                day: i64::try_from(day).unwrap_or(0),
                items,
            }),
            kind: "scan",
            note,
        });
    }
    file
}

/// Extrait de `Auctionator.lua` le dernier scan complet de chaque royaume. Une base illisible ou d'un autre
/// format ne donne rien.
pub fn extract_auctionator(lua: &[u8]) -> Vec<AuctionatorScan> {
    read_auctionator(lua)
        .realms
        .into_iter()
        .filter_map(|realm| realm.scan)
        .collect()
}

/// L'empreinte des prix d'un scan (FNV-1a sur chaque objet et son prix), réduite à 53 bits : elle est gardée dans
/// la configuration, que la fenêtre lit en JavaScript.
fn fingerprint(items: &[(u32, u64, Option<u32>)]) -> i64 {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    for (id, price, _) in items {
        for byte in id.to_le_bytes().iter().chain(price.to_le_bytes().iter()) {
            hash ^= u64::from(*byte);
            hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
        }
    }
    (hash >> 11) as i64
}

/// L'heure de la dernière écriture d'un fichier, en secondes.
fn modified_at(path: &Path) -> Option<i64> {
    let modified = fs::metadata(path).ok()?.modified().ok()?;
    let seconds = modified
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_secs();
    i64::try_from(seconds).ok()
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum AuctionOutcome {
    /// Le site refuse les prix de ce compte : aucun fichier n'a été lu.
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

/// Envoie un scan et retient qu'il l'a été : `mark` sous `key` dans `config.last_auction_scans`. `label` : le
/// nom montré au joueur.
fn send(
    client: &SiteClient,
    config: &mut Config,
    scan: &HouseScan,
    key: String,
    mark: i64,
    label: String,
) -> AuctionOutcome {
    match client.upload_auctions(scan) {
        Ok(()) => {
            config.last_auction_scans.insert(key, mark);
            AuctionOutcome::Sent {
                house: label,
                scanned_at: scan.scanned_at,
                items: scan.items.len(),
            }
        }
        Err(CoreError::Duplicate) => {
            config.last_auction_scans.insert(key, mark);
            AuctionOutcome::Duplicate { house: label }
        }
        Err(e) => AuctionOutcome::Failed {
            error: format!("{label} : {e}"),
        },
    }
}

/// Ce que le compagnon a fait d'un fichier de scan, dit au site (page Tests, GM) : on y lit pourquoi un scan
/// n'arrive pas sans demander son fichier au joueur.
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct ScanReport {
    /// L'addon lu : `SCAN_ADDON` ou `AUCTIONATOR`.
    pub source: String,
    /// L'hôtel ou le royaume, tel que l'addon l'écrit ; vide quand le constat porte sur le fichier.
    pub house: String,
    /// sent, duplicate, unchanged, failed, unreadable, no_scan, no_file, not_allowed.
    pub kind: String,
    pub detail: String,
    /// Le jour du scan, compté par Auctionator.
    pub day: Option<i64>,
    pub items: Option<usize>,
    pub scanned_at: Option<i64>,
    /// L'heure d'écriture du fichier lu.
    pub file_at: Option<i64>,
}

impl ScanReport {
    fn new(source: &str, house: &str, kind: &str, detail: String) -> Self {
        Self {
            source: source.to_string(),
            house: house.to_string(),
            kind: kind.to_string(),
            detail,
            day: None,
            items: None,
            scanned_at: None,
            file_at: None,
        }
    }

    /// Le constat d'un envoi : ce que le site a répondu, avec `note` (ce qu'on avait lu) quand il n'a rien à dire.
    fn of(source: &str, house: &str, outcome: &AuctionOutcome, note: &str) -> Self {
        match outcome {
            AuctionOutcome::Sent {
                scanned_at, items, ..
            } => {
                let mut report = Self::new(source, house, "sent", note.to_string());
                report.scanned_at = Some(*scanned_at);
                report.items = Some(*items);
                report
            }
            AuctionOutcome::Duplicate { .. } => Self::new(
                source,
                house,
                "duplicate",
                "le site a déjà ce scan, ou un autre de cet hôtel à moins de 30 minutes".to_string(),
            ),
            AuctionOutcome::Unchanged { .. } => Self::new(
                source,
                house,
                "unchanged",
                "déjà envoyé : rien de nouveau depuis".to_string(),
            ),
            AuctionOutcome::Failed { error } => Self::new(source, house, "failed", error.clone()),
            AuctionOutcome::NotAllowed => Self::new(
                source,
                house,
                "not_allowed",
                "le site refuse les prix de ce compte".to_string(),
            ),
        }
    }
}

/// Un passage : s'il existe un fichier de scan (NaowhForever ou Auctionator) et que le site autorise ce compte,
/// envoie les scans plus récents que le dernier envoyé. Met à jour `config.last_auction_scans` (à sauvegarder par
/// l'appelant) : l'heure du scan par hôtel pour NaowhForever ; pour Auctionator, le jour du scan sous
/// « Auctionator:<royaume> » et l'empreinte de ses prix sous « Auctionator:<royaume>:prix » (les mêmes prix le
/// même jour ne repartent pas, d'autres prix si). Ne touche à rien d'autre : un échec ici n'empêche jamais
/// l'envoi des personnages.
pub fn upload_once(
    game_dir: &Path,
    config: &mut Config,
    client: &SiteClient,
) -> Vec<AuctionOutcome> {
    upload_with_reports(game_dir, config, client).0
}

/// `upload_once`, avec en plus un constat par fichier et par royaume (0.7.12), à envoyer au site par l'appelant.
pub fn upload_with_reports(
    game_dir: &Path,
    config: &mut Config,
    client: &SiteClient,
) -> (Vec<AuctionOutcome>, Vec<ScanReport>) {
    let mut outcomes = Vec::new();
    let mut reports = Vec::new();
    if !config.is_paired() {
        return (outcomes, reports);
    }
    let files = find_scan_files(game_dir);
    let auctionator_files = find_addon_files(game_dir, AUCTIONATOR);
    if files.is_empty() && auctionator_files.is_empty() {
        reports.push(ScanReport::new(
            AUCTIONATOR,
            "",
            "no_file",
            "ni Auctionator.lua ni NaowhForever.lua dans les comptes de ce dossier de jeu".to_string(),
        ));
        return (outcomes, reports);
    }
    match client.auction_rights() {
        Ok(true) => {}
        Ok(false) => {
            outcomes.push(AuctionOutcome::NotAllowed);
            return (outcomes, reports);
        }
        // Droit inconnu (site injoignable, jeton révoqué) : on ne dit rien, cette fonction n'existe pas pour qui
        // n'y a pas droit ; l'envoi des personnages signale déjà ces pannes.
        Err(e) => {
            log::warn!("hôtel des ventes : droit d'envoi inconnu ({e})");
            return (outcomes, reports);
        }
    }
    for file in files {
        let text = match fs::read(&file) {
            Ok(bytes) => String::from_utf8_lossy(&bytes).into_owned(),
            Err(e) => {
                let outcome = AuctionOutcome::Failed {
                    error: e.to_string(),
                };
                reports.push(ScanReport::of(SCAN_ADDON, "", &outcome, ""));
                outcomes.push(outcome);
                continue;
            }
        };
        let file_at = modified_at(&file);
        let scans = extract_scans(&text);
        if scans.is_empty() {
            let mut report = ScanReport::new(
                SCAN_ADDON,
                "",
                "no_scan",
                "aucun scan complet dans le fichier".to_string(),
            );
            report.file_at = file_at;
            reports.push(report);
        }
        for scan in scans {
            let house = scan.house.clone();
            let known = config.last_auction_scans.get(&house).copied().unwrap_or(0);
            let outcome = if scan.scanned_at <= known {
                AuctionOutcome::Unchanged {
                    house: house.clone(),
                }
            } else {
                let mark = scan.scanned_at;
                send(client, config, &scan, house.clone(), mark, house.clone())
            };
            let mut report = ScanReport::of(SCAN_ADDON, &house, &outcome, "");
            report.file_at = file_at;
            report.items = Some(scan.items.len());
            report.scanned_at = Some(scan.scanned_at);
            reports.push(report);
            outcomes.push(outcome);
        }
    }
    for file in auctionator_files {
        let bytes = match fs::read(&file) {
            Ok(bytes) => bytes,
            Err(e) => {
                let outcome = AuctionOutcome::Failed {
                    error: e.to_string(),
                };
                reports.push(ScanReport::of(AUCTIONATOR, "", &outcome, ""));
                outcomes.push(outcome);
                continue;
            }
        };
        let Some(modified) = modified_at(&file) else {
            reports.push(ScanReport::new(
                AUCTIONATOR,
                "",
                "failed",
                "date d'écriture du fichier illisible".to_string(),
            ));
            continue;
        };
        let read = read_auctionator(&bytes);
        let version = match read.version {
            Some(version) => format!(" · base version {version}"),
            None => String::new(),
        };
        if !read.found || read.realms.is_empty() {
            let detail = if read.found {
                "base de prix vide : aucun royaume"
            } else {
                "pas de base de prix (AUCTIONATOR_PRICE_DATABASE) dans le fichier"
            };
            let mut report =
                ScanReport::new(AUCTIONATOR, "", "unreadable", format!("{detail}{version}"));
            report.file_at = Some(modified);
            reports.push(report);
            continue;
        }
        for realm in read.realms {
            let note = format!("{}{version}", realm.note);
            let Some(found) = realm.scan else {
                let mut report = ScanReport::new(AUCTIONATOR, &realm.house, realm.kind, note);
                report.file_at = Some(modified);
                reports.push(report);
                continue;
            };
            let label = format!("{} ({AUCTIONATOR})", found.house);
            let key = format!("{AUCTIONATOR}:{}", found.house);
            let print_key = format!("{key}:prix");
            let print = fingerprint(&found.items);
            let known = config.last_auction_scans.get(&key).copied().unwrap_or(-1);
            // Le même jour : un nouveau scan si les prix ont changé. Sans empreinte retenue (jour envoyé par une
            // version d'avant), il repart une fois : le site reconnaît le sien s'il l'a déjà.
            let same_prices = config.last_auction_scans.get(&print_key).copied() == Some(print);
            // Le fichier est écrit à la déconnexion qui suit le scan ; s'il l'a été bien plus tard, la date reste
            // dans le jour du scan (à douze heures près : le fuseau du joueur n'est pas connu).
            let day_end = AUCTIONATOR_DAY_0 + (found.day + 1) * 86_400 + 43_200;
            let scanned_at = modified.min(day_end);
            let (day, count) = (found.day, found.items.len());
            let outcome = if day < known || (day == known && same_prices) {
                AuctionOutcome::Unchanged { house: label }
            } else {
                let scan = HouseScan {
                    house: found.house,
                    scanned_at,
                    items: found.items,
                };
                let outcome = send(client, config, &scan, key, day, label);
                if matches!(
                    outcome,
                    AuctionOutcome::Sent { .. } | AuctionOutcome::Duplicate { .. }
                ) {
                    config.last_auction_scans.insert(print_key, print);
                }
                outcome
            };
            let mut report = ScanReport::of(AUCTIONATOR, &realm.house, &outcome, &note);
            if !matches!(outcome, AuctionOutcome::Sent { .. }) {
                report.detail = format!("{} ({note})", report.detail);
            }
            report.day = Some(day);
            report.items = Some(count);
            report.scanned_at = Some(scanned_at);
            report.file_at = Some(modified);
            reports.push(report);
            outcomes.push(outcome);
        }
    }
    (outcomes, reports)
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

    fn cbor_text(text: &str) -> Vec<u8> {
        let mut out = vec![0x40 | text.len() as u8];
        out.extend(text.as_bytes());
        out
    }

    fn cbor_uint(n: u16) -> Vec<u8> {
        vec![0x19, (n >> 8) as u8, n as u8]
    }

    fn cbor_map(pairs: &[(Vec<u8>, Vec<u8>)]) -> Vec<u8> {
        let mut out = vec![0xb9, (pairs.len() >> 8) as u8, pairs.len() as u8];
        for (key, value) in pairs {
            out.extend(key);
            out.extend(value);
        }
        out
    }

    /// `Auctionator.lua` avec cette base pour le royaume « PvP », écrite comme le fait le client.
    fn auctionator_file(database: &[u8]) -> Vec<u8> {
        let mut out = b"AUCTIONATOR_CONFIG = {\n}\nAUCTIONATOR_PRICE_DATABASE = {\n[\"__dbversion\"] = 8,\n[\"PvP\"] = \"".to_vec();
        for byte in database {
            match byte {
                b'\\' => out.extend(b"\\\\"),
                b'"' => out.extend(b"\\\""),
                b'\n' => out.extend(b"\\n"),
                b'\r' => out.extend(b"\\r"),
                0 => out.extend(b"\\000"),
                other => out.push(*other),
            }
        }
        out.extend(b"\",\n}\nAUCTIONATOR_POSTING_HISTORY = {\n}\n");
        out
    }

    /// 250 objets : les 240 premiers vus le jour 2507 (le scan complet), les autres le jour 2501 seulement.
    fn auctionator_database(scan_day: &str) -> Vec<u8> {
        auctionator_database_priced(scan_day, 10)
    }

    /// La même base, chaque objet au prix de `factor` fois son numéro.
    fn auctionator_database_priced(scan_day: &str, factor: u16) -> Vec<u8> {
        let mut entries = vec![(cbor_text("version"), vec![0x02])];
        for id in 1..=250u16 {
            let day = if id <= 240 { scan_day } else { "2501" };
            entries.push((
                cbor_text(&id.to_string()),
                cbor_map(&[
                    (cbor_text("a"), cbor_map(&[(cbor_text(day), cbor_uint(3))])),
                    (cbor_text("l"), vec![0x80]),
                    (cbor_text("m"), cbor_uint(id * factor)),
                    (
                        cbor_text("h"),
                        cbor_map(&[
                            (cbor_text("2500"), cbor_uint(1)),
                            (cbor_text(day), cbor_uint(id * factor)),
                        ]),
                    ),
                ]),
            ));
        }
        cbor_map(&entries)
    }

    #[test]
    fn reads_the_last_full_scan_of_auctionator() {
        let scans = extract_auctionator(&auctionator_file(&auctionator_database("2507")));
        assert_eq!(scans.len(), 1);
        assert_eq!(scans[0].house, "PvP");
        assert_eq!(scans[0].day, 2507);
        assert_eq!(scans[0].items.len(), 240);
        assert_eq!(scans[0].items[0], (1, 10, None));
        assert_eq!(scans[0].items[239], (240, 2400, None));
        // Quelques recherches à la main ne font pas un scan ; une base coupée ou d'un autre format non plus.
        let mut few = vec![(cbor_text("version"), vec![0x02])];
        few.push((
            cbor_text("2589"),
            cbor_map(&[
                (cbor_text("m"), cbor_uint(100)),
                (cbor_text("h"), cbor_map(&[(cbor_text("2507"), cbor_uint(100))])),
            ]),
        ));
        assert!(extract_auctionator(&auctionator_file(&cbor_map(&few))).is_empty());
        let whole = auctionator_database("2507");
        assert!(extract_auctionator(&auctionator_file(&whole[..whole.len() - 4])).is_empty());
        assert!(extract_auctionator(b"AUCTIONATOR_PRICE_DATABASE = {\n[\"PvP\"] = {\n},\n}\n").is_empty());
    }

    #[test]
    fn sends_an_auctionator_scan_when_its_prices_change_without_auction_counts() {
        let tmp = tempfile::tempdir().unwrap();
        let dir = tmp.path().join("WTF/Account/WOW1/SavedVariables");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(
            dir.join("Auctionator.lua"),
            auctionator_file(&auctionator_database("2507")),
        )
        .unwrap();
        let server = MockServer::start();
        status(&server, true);
        let upload = server.mock(|when, then| {
            when.method(POST)
                .path("/api/sync/auctions/")
                .json_body_partial(r#"{ "house": "PvP" }"#);
            then.status(201).json_body(serde_json::json!({ "id": 1 }));
        });
        let client = SiteClient::new(&server.base_url(), Some("tok".into()));
        let mut config = Config::default();
        config.token = Some("tok".into());
        let outcomes = upload_once(tmp.path(), &mut config, &client);
        assert!(matches!(
            &outcomes[0],
            AuctionOutcome::Sent { house, items: 240, .. } if house == "PvP (Auctionator)"
        ));
        assert_eq!(config.last_auction_scans["Auctionator:PvP"], 2507);
        assert_eq!(
            upload_once(tmp.path(), &mut config, &client),
            vec![AuctionOutcome::Unchanged {
                house: "PvP (Auctionator)".into()
            }]
        );
        assert_eq!(upload.hits(), 1);
        // Un second scan le même jour, d'autres prix : il part ; puis plus rien tant que rien ne change.
        std::fs::write(
            dir.join("Auctionator.lua"),
            auctionator_file(&auctionator_database_priced("2507", 11)),
        )
        .unwrap();
        let outcomes = upload_once(tmp.path(), &mut config, &client);
        assert!(matches!(
            &outcomes[0],
            AuctionOutcome::Sent { house, items: 240, .. } if house == "PvP (Auctionator)"
        ));
        assert_eq!(config.last_auction_scans["Auctionator:PvP"], 2507);
        assert_eq!(upload.hits(), 2);
        assert!(matches!(
            &upload_once(tmp.path(), &mut config, &client)[0],
            AuctionOutcome::Unchanged { .. }
        ));
        assert_eq!(upload.hits(), 2);
        // Le constat pour le site : rien de nouveau, avec ce qu'on a lu.
        let (_, reports) = upload_with_reports(tmp.path(), &mut config, &client);
        assert_eq!(reports.len(), 1);
        assert_eq!(
            (reports[0].source.as_str(), reports[0].house.as_str(), reports[0].kind.as_str()),
            ("Auctionator", "PvP", "unchanged")
        );
        assert_eq!((reports[0].day, reports[0].items), (Some(2507), Some(240)));
        assert!(reports[0].detail.contains("240 objets") && reports[0].detail.contains("base version 8"));
        // Un jour envoyé par une version d'avant, sans empreinte : il repart une fois.
        config.last_auction_scans.remove("Auctionator:PvP:prix");
        upload_once(tmp.path(), &mut config, &client);
        assert_eq!(upload.hits(), 3);
        assert!(config.last_auction_scans.contains_key("Auctionator:PvP:prix"));
    }

    #[test]
    fn reports_say_why_no_scan_left() {
        let tmp = tempfile::tempdir().unwrap();
        let dir = tmp.path().join("WTF/Account/WOW1/SavedVariables");
        std::fs::create_dir_all(&dir).unwrap();
        let server = MockServer::start();
        status(&server, true);
        let client = SiteClient::new(&server.base_url(), Some("tok".into()));
        let mut config = Config::default();
        config.token = Some("tok".into());
        // Aucun fichier de scan : un constat, sans rien demander au site.
        let (outcomes, reports) = upload_with_reports(tmp.path(), &mut config, &client);
        assert!(outcomes.is_empty());
        assert_eq!(reports[0].kind, "no_file");
        // Une base en table Lua (autre version d'Auctionator) et une base sans scan complet.
        let mut few = vec![(cbor_text("version"), vec![0x02])];
        few.push((
            cbor_text("2589"),
            cbor_map(&[
                (cbor_text("m"), cbor_uint(100)),
                (cbor_text("h"), cbor_map(&[(cbor_text("2507"), cbor_uint(100))])),
            ]),
        ));
        let mut file = auctionator_file(&cbor_map(&few));
        let marker = b"AUCTIONATOR_PRICE_DATABASE = {\n";
        let at = file
            .windows(marker.len())
            .position(|window| window == marker)
            .unwrap()
            + marker.len();
        drop(file.splice(at..at, b"[\"PvE\"] = {\n".iter().copied()));
        std::fs::write(dir.join("Auctionator.lua"), &file).unwrap();
        let (outcomes, reports) = upload_with_reports(tmp.path(), &mut config, &client);
        assert!(outcomes.is_empty());
        assert_eq!(reports.len(), 2);
        assert_eq!(
            (reports[0].house.as_str(), reports[0].kind.as_str()),
            ("PvE", "unreadable")
        );
        assert!(reports[0].detail.contains("table Lua"));
        assert_eq!(
            (reports[1].house.as_str(), reports[1].kind.as_str()),
            ("PvP", "no_scan")
        );
        assert!(reports[1]
            .detail
            .contains("pas de scan complet : 1 objets lisibles"));
        assert!(config.last_auction_scans.is_empty());
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
