//! Le sous-ensemble de Lua qu'écrit le client dans `SavedVariables` : affectations de tables, clés `["texte"]`
//! ou `[nombre]`, valeurs texte, nombre, booléen, table. Lu et réécrit tel quel, dans l'ordre du fichier.

use std::fmt::Write as _;

#[derive(Debug, Clone, PartialEq)]
pub enum Key {
    Int(i64),
    Str(String),
}

#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Bool(bool),
    Num(f64),
    Str(String),
    Table(Table),
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct Table {
    pub entries: Vec<(Key, Value)>,
}

impl Table {
    pub fn get(&self, key: &str) -> Option<&Value> {
        self.entries
            .iter()
            .find(|(k, _)| matches!(k, Key::Str(s) if s == key))
            .map(|(_, v)| v)
    }

    pub fn get_mut(&mut self, key: &str) -> Option<&mut Value> {
        self.entries
            .iter_mut()
            .find(|(k, _)| matches!(k, Key::Str(s) if s == key))
            .map(|(_, v)| v)
    }

    pub fn get_num(&self, key: &str) -> Option<f64> {
        match self.get(key) {
            Some(Value::Num(n)) => Some(*n),
            _ => None,
        }
    }

    pub fn get_str(&self, key: &str) -> Option<&str> {
        match self.get(key) {
            Some(Value::Str(s)) => Some(s),
            _ => None,
        }
    }

    pub fn get_table(&self, key: &str) -> Option<&Table> {
        match self.get(key) {
            Some(Value::Table(t)) => Some(t),
            _ => None,
        }
    }

    /// Remplace la valeur de `key`, ou l'ajoute en fin de table.
    pub fn set(&mut self, key: &str, value: Value) {
        match self.get_mut(key) {
            Some(slot) => *slot = value,
            None => self.entries.push((Key::Str(key.to_string()), value)),
        }
    }

    pub fn remove(&mut self, key: &str) {
        self.entries
            .retain(|(k, _)| !matches!(k, Key::Str(s) if s == key));
    }

    /// La sous-table `key`, créée vide si elle manque ou n'est pas une table.
    pub fn table_mut(&mut self, key: &str) -> &mut Table {
        let is_table = matches!(self.get(key), Some(Value::Table(_)));
        if !is_table {
            self.set(key, Value::Table(Table::default()));
        }
        match self.get_mut(key) {
            Some(Value::Table(t)) => t,
            _ => unreachable!("table créée juste avant"),
        }
    }
}

// --- lecture -------------------------------------------------------------------------------------------

struct Parser<'a> {
    s: &'a [u8],
    i: usize,
}

type ParseResult<T> = std::result::Result<T, String>;

impl<'a> Parser<'a> {
    fn peek(&self) -> Option<u8> {
        self.s.get(self.i).copied()
    }

    fn error<T>(&self, what: &str) -> ParseResult<T> {
        let line = self.s[..self.i.min(self.s.len())]
            .iter()
            .filter(|&&c| c == b'\n')
            .count()
            + 1;
        Err(format!("{what} (ligne {line})"))
    }

    /// Blancs et commentaires `-- …` (le client en écrit après les valeurs des tableaux).
    fn skip(&mut self) {
        loop {
            match self.peek() {
                Some(c) if c.is_ascii_whitespace() => self.i += 1,
                Some(b'-') if self.s.get(self.i + 1) == Some(&b'-') => {
                    while let Some(c) = self.peek() {
                        self.i += 1;
                        if c == b'\n' {
                            break;
                        }
                    }
                }
                _ => return,
            }
        }
    }

    fn expect(&mut self, c: u8) -> ParseResult<()> {
        self.skip();
        if self.peek() == Some(c) {
            self.i += 1;
            Ok(())
        } else {
            self.error(&format!("« {} » attendu", c as char))
        }
    }

    fn identifier(&mut self) -> ParseResult<String> {
        self.skip();
        let start = self.i;
        while let Some(c) = self.peek() {
            if c.is_ascii_alphanumeric() || c == b'_' {
                self.i += 1;
            } else {
                break;
            }
        }
        if start == self.i {
            return self.error("nom attendu");
        }
        Ok(String::from_utf8_lossy(&self.s[start..self.i]).to_string())
    }

    fn string(&mut self) -> ParseResult<String> {
        let quote = self.peek().unwrap_or(b'"');
        self.i += 1;
        let mut out: Vec<u8> = Vec::new();
        loop {
            let Some(c) = self.peek() else {
                return self.error("chaîne non terminée");
            };
            self.i += 1;
            match c {
                c if c == quote => break,
                b'\\' => {
                    let Some(e) = self.peek() else {
                        return self.error("chaîne non terminée");
                    };
                    self.i += 1;
                    match e {
                        b'n' => out.push(b'\n'),
                        b'r' => out.push(b'\r'),
                        b't' => out.push(b'\t'),
                        b'a' => out.push(7),
                        b'b' => out.push(8),
                        b'f' => out.push(12),
                        b'v' => out.push(11),
                        b'0'..=b'9' => {
                            let mut n: u32 = (e - b'0') as u32;
                            for _ in 0..2 {
                                match self.peek() {
                                    Some(d) if d.is_ascii_digit() => {
                                        n = n * 10 + (d - b'0') as u32;
                                        self.i += 1;
                                    }
                                    _ => break,
                                }
                            }
                            out.push((n & 0xff) as u8);
                        }
                        b'\n' => out.push(b'\n'),
                        other => out.push(other),
                    }
                }
                other => out.push(other),
            }
        }
        Ok(String::from_utf8_lossy(&out).to_string())
    }

    fn number(&mut self) -> ParseResult<f64> {
        let start = self.i;
        while let Some(c) = self.peek() {
            if c.is_ascii_alphanumeric() || matches!(c, b'.' | b'-' | b'+') {
                self.i += 1;
            } else {
                break;
            }
        }
        let text = String::from_utf8_lossy(&self.s[start..self.i]).to_string();
        let parsed = if let Some(hex) = text.strip_prefix("0x").or_else(|| text.strip_prefix("0X"))
        {
            i64::from_str_radix(hex, 16).ok().map(|n| n as f64)
        } else {
            match text.as_str() {
                "inf" | "1e9999" => Some(f64::INFINITY),
                "-inf" | "-1e9999" => Some(f64::NEG_INFINITY),
                _ => text.parse::<f64>().ok(),
            }
        };
        match parsed {
            Some(n) => Ok(n),
            None => self.error(&format!("nombre illisible « {text} »")),
        }
    }

    fn value(&mut self) -> ParseResult<Option<Value>> {
        self.skip();
        match self.peek() {
            Some(b'{') => {
                self.i += 1;
                Ok(Some(Value::Table(self.table()?)))
            }
            Some(b'"') | Some(b'\'') => Ok(Some(Value::Str(self.string()?))),
            Some(c) if c.is_ascii_digit() || c == b'-' || c == b'.' => {
                Ok(Some(Value::Num(self.number()?)))
            }
            Some(c) if c.is_ascii_alphabetic() => {
                let word = self.identifier()?;
                match word.as_str() {
                    "true" => Ok(Some(Value::Bool(true))),
                    "false" => Ok(Some(Value::Bool(false))),
                    "nil" => Ok(None),
                    "inf" | "nan" => Ok(Some(Value::Num(f64::NAN))),
                    _ => self.error(&format!("valeur inconnue « {word} »")),
                }
            }
            _ => self.error("valeur attendue"),
        }
    }

    /// Après le `{` ouvrant, jusqu'au `}` fermant inclus.
    fn table(&mut self) -> ParseResult<Table> {
        let mut table = Table::default();
        let mut next_index: i64 = 1;
        loop {
            self.skip();
            match self.peek() {
                None => return self.error("table non terminée"),
                Some(b'}') => {
                    self.i += 1;
                    return Ok(table);
                }
                Some(b',') | Some(b';') => {
                    self.i += 1;
                    continue;
                }
                Some(b'[') => {
                    self.i += 1;
                    let key = match self.value()? {
                        Some(Value::Str(s)) => Key::Str(s),
                        Some(Value::Num(n)) if n.fract() == 0.0 => Key::Int(n as i64),
                        Some(Value::Num(n)) => Key::Str(n.to_string()),
                        _ => return self.error("clé illisible"),
                    };
                    self.expect(b']')?;
                    self.expect(b'=')?;
                    if let Some(v) = self.value()? {
                        if let Key::Int(n) = key {
                            next_index = next_index.max(n + 1);
                        }
                        table.entries.push((key, v));
                    }
                }
                Some(c) if c.is_ascii_alphabetic() || c == b'_' => {
                    // `nom = valeur`, ou une valeur nue (true, false, nil).
                    let save = self.i;
                    let word = self.identifier()?;
                    self.skip();
                    if self.peek() == Some(b'=') && self.s.get(self.i + 1) != Some(&b'=') {
                        self.i += 1;
                        if let Some(v) = self.value()? {
                            table.entries.push((Key::Str(word), v));
                        }
                    } else {
                        self.i = save;
                        if let Some(v) = self.value()? {
                            table.entries.push((Key::Int(next_index), v));
                        }
                        next_index += 1;
                    }
                }
                Some(_) => {
                    if let Some(v) = self.value()? {
                        table.entries.push((Key::Int(next_index), v));
                    }
                    next_index += 1;
                }
            }
        }
    }
}

/// Toutes les affectations `nom = valeur` du fichier, dans l'ordre.
pub fn parse_file(text: &str) -> ParseResult<Vec<(String, Value)>> {
    let mut p = Parser {
        s: text.as_bytes(),
        i: 0,
    };
    let mut out = Vec::new();
    loop {
        p.skip();
        if p.peek().is_none() {
            return Ok(out);
        }
        let name = p.identifier()?;
        p.expect(b'=')?;
        match p.value()? {
            Some(v) => out.push((name, v)),
            None => {}
        }
        p.skip();
        if p.peek() == Some(b';') {
            p.i += 1;
        }
    }
}

// --- écriture ------------------------------------------------------------------------------------------

fn write_string(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 32 || c as u32 == 127 => {
                let _ = write!(out, "\\{:03}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

fn write_number(out: &mut String, n: f64) {
    if n.is_nan() {
        out.push_str("0/0");
    } else if n.is_infinite() {
        out.push_str(if n > 0.0 { "1e9999" } else { "-1e9999" });
    } else if n.fract() == 0.0 && n.abs() < 9_007_199_254_740_992.0 {
        let _ = write!(out, "{}", n as i64);
    } else {
        let _ = write!(out, "{n}");
    }
}

fn write_value(out: &mut String, value: &Value, depth: usize) {
    match value {
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Num(n) => write_number(out, *n),
        Value::Str(s) => write_string(out, s),
        Value::Table(t) => {
            if t.entries.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push_str("{\n");
            for (key, v) in &t.entries {
                for _ in 0..=depth {
                    out.push('\t');
                }
                match key {
                    Key::Int(n) => {
                        let _ = write!(out, "[{n}] = ");
                    }
                    Key::Str(s) => {
                        out.push('[');
                        write_string(out, s);
                        out.push_str("] = ");
                    }
                }
                write_value(out, v, depth + 1);
                out.push_str(",\n");
            }
            for _ in 0..depth {
                out.push('\t');
            }
            out.push('}');
        }
    }
}

/// Le fichier complet : une affectation par variable, comme l'écrit le client.
pub fn write_file(assignments: &[(String, Value)]) -> String {
    let mut out = String::new();
    for (name, value) in assignments {
        out.push_str(name);
        out.push_str(" = ");
        write_value(&mut out, value, 0);
        out.push('\n');
    }
    out
}

// --- depuis le JSON du site --------------------------------------------------------------------------

/// Valeur JSON → Lua : objets en tables à clés texte, tableaux en tables 1..n, `null` ignoré.
pub fn from_json(value: &serde_json::Value) -> Option<Value> {
    use serde_json::Value as J;
    match value {
        J::Null => None,
        J::Bool(b) => Some(Value::Bool(*b)),
        J::Number(n) => n.as_f64().map(Value::Num),
        J::String(s) => Some(Value::Str(s.clone())),
        J::Array(items) => {
            let mut table = Table::default();
            for (i, item) in items.iter().enumerate() {
                if let Some(v) = from_json(item) {
                    table.entries.push((Key::Int(i as i64 + 1), v));
                }
            }
            Some(Value::Table(table))
        }
        J::Object(map) => {
            let mut table = Table::default();
            for (k, item) in map {
                if let Some(v) = from_json(item) {
                    table.entries.push((Key::Str(k.clone()), v));
                }
            }
            Some(Value::Table(table))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"
WoWForeverGuildeDB = {
	["version"] = 1,
	["installId"] = "k2j3h4g5",
	["settings"] = {
		["sharePlaytime"] = false,
		["excluded"] = {
		},
	},
	["characters"] = {
		["Player-1-000ABC01"] = {
			["name"] = "Thrall",
			["counters"] = {
				["deaths"] = 14,
				["gathering"] = {
					["mining"] = 310.5,
				},
			},
			["events"] = {
				{
					["k"] = "level",
					["t"] = 1764000000,
				}, -- [1]
				{
					["k"] = "death",
					["zone"] = "Forêt d\"Elwynn \124cff00ff00vert\124r",
				}, -- [2]
			},
			["lockouts"] = {
			},
			["updated_at"] = 1764000100,
		},
	},
}
"#;

    fn db(text: &str) -> Table {
        let parsed = parse_file(text).unwrap();
        match &parsed[0].1 {
            Value::Table(t) => t.clone(),
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn reads_the_client_format() {
        let db = db(SAMPLE);
        assert_eq!(db.get_num("version"), Some(1.0));
        assert_eq!(db.get_str("installId"), Some("k2j3h4g5"));
        let thrall = db
            .get_table("characters")
            .unwrap()
            .get_table("Player-1-000ABC01")
            .unwrap();
        let counters = thrall.get_table("counters").unwrap();
        assert_eq!(counters.get_num("deaths"), Some(14.0));
        assert_eq!(
            counters.get_table("gathering").unwrap().get_num("mining"),
            Some(310.5)
        );
        let events = thrall.get_table("events").unwrap();
        assert_eq!(events.entries.len(), 2);
        assert!(matches!(events.entries[1].0, Key::Int(2)));
        let Value::Table(death) = &events.entries[1].1 else {
            panic!()
        };
        assert_eq!(
            death.get_str("zone"),
            Some("Forêt d\"Elwynn |cff00ff00vert|r")
        );
        assert_eq!(thrall.get_table("lockouts").unwrap().entries.len(), 0);
        assert!(
            db.get_table("settings").unwrap().get("sharePlaytime") == Some(&Value::Bool(false))
        );
    }

    #[test]
    fn round_trips_through_writer() {
        let parsed = parse_file(SAMPLE).unwrap();
        let text = write_file(&parsed);
        assert!(text.starts_with("WoWForeverGuildeDB = {\n\t[\"version\"] = 1,"));
        assert!(text.contains("[1] = {"));
        assert!(text.contains(r#"["zone"] = "Forêt d\"Elwynn |cff00ff00vert|r","#));
        let again = parse_file(&text).unwrap();
        assert_eq!(again, parsed);
        // Ce que l'addon relit : le code d'export reste extractible par le compagnon.
        let mut db = db(SAMPLE);
        db.set("export", Value::Str("WFG1:00000000:AAAA".into()));
        let text = write_file(&[("WoWForeverGuildeDB".into(), Value::Table(db))]);
        assert!(crate::savedvars::extract_export(&text).is_some());
    }

    #[test]
    fn json_becomes_lua() {
        let json = serde_json::json!({ "counters": { "deaths": 2, "mobs": { "Loup": 3 } }, "events": [ { "k": "death", "t": 5 } ], "none": null, "ok": true, "ratio": 0.5 });
        let Value::Table(t) = from_json(&json).unwrap() else {
            panic!()
        };
        assert!(t.get("none").is_none());
        assert_eq!(t.get("ok"), Some(&Value::Bool(true)));
        assert_eq!(t.get_num("ratio"), Some(0.5));
        let events = t.get_table("events").unwrap();
        assert!(matches!(events.entries[0].0, Key::Int(1)));
        let text = write_file(&[("X".into(), Value::Table(t))]);
        assert!(text.contains("[\"Loup\"] = 3,") && text.contains("[\"ratio\"] = 0.5,"));
    }

    #[test]
    fn set_and_table_mut() {
        let mut t = Table::default();
        t.table_mut("a").set("b", Value::Num(1.0));
        t.set("a", Value::Num(2.0)); // remplacé, même position
        t.set("c", Value::Bool(true));
        assert_eq!(t.entries.len(), 2);
        assert_eq!(t.get_num("a"), Some(2.0));
        t.table_mut("a").set("x", Value::Num(3.0)); // redevient une table
        assert_eq!(t.get_table("a").unwrap().get_num("x"), Some(3.0));
        t.remove("c");
        assert!(t.get("c").is_none());
    }
}
