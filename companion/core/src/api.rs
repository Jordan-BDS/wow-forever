//! Le site : appairage (code → jeton), import d'un code d'export, état du compagnon.

use serde::{Deserialize, Serialize};

use crate::error::{CoreError, Result};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Device {
    pub id: i64,
    pub name: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PairResponse {
    pub token: String,
    pub device: Device,
    pub display_name: String,
}

#[derive(Debug, Clone, Deserialize, Default, PartialEq, Eq)]
pub struct Summary {
    #[serde(default)]
    pub applied: u32,
    #[serde(default)]
    pub created: u32,
    #[serde(default)]
    pub pending: u32,
    #[serde(default)]
    pub ignored: u32,
    #[serde(default)]
    pub stale: u32,
    #[serde(default)]
    pub refused: u32,
    #[serde(default)]
    pub new_recipes: u32,
}

impl Summary {
    /// « 2 mis à jour, 1 créé, 12 nouvelles recettes »
    pub fn describe(&self) -> String {
        let mut parts = Vec::new();
        let plural = |n: u32, one: &str, many: &str| {
            if n > 1 {
                format!("{n} {many}")
            } else {
                format!("{n} {one}")
            }
        };
        if self.applied > 0 {
            parts.push(format!("{} mis à jour", self.applied));
        }
        if self.created > 0 {
            parts.push(plural(self.created, "créé", "créés"));
        }
        if self.pending > 0 {
            parts.push(format!("{} à rattacher", self.pending));
        }
        if self.ignored > 0 {
            parts.push(plural(self.ignored, "ignoré", "ignorés"));
        }
        if self.stale > 0 {
            parts.push(format!("{} déjà à jour", self.stale));
        }
        if self.refused > 0 {
            parts.push(plural(self.refused, "refusé", "refusés"));
        }
        if self.new_recipes > 0 {
            parts.push(plural(
                self.new_recipes,
                "nouvelle recette",
                "nouvelles recettes",
            ));
        }
        if parts.is_empty() {
            "rien de nouveau".to_string()
        } else {
            parts.join(", ")
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct Snapshot {
    pub full_name: String,
    pub status: String,
    #[serde(default)]
    pub note: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ImportBatch {
    pub id: i64,
    pub received_at: String,
    #[serde(default)]
    pub summary: Summary,
    #[serde(default)]
    pub snapshots: Vec<Snapshot>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CompanionStatus {
    pub display_name: String,
    pub device: Device,
    pub last_import: Option<ImportBatch>,
}

#[derive(Debug, Deserialize)]
struct ErrorBody {
    #[serde(default)]
    detail: Option<String>,
    #[serde(default)]
    code: Option<serde_json::Value>,
}

pub struct SiteClient {
    base_url: String,
    token: Option<String>,
    http: reqwest::blocking::Client,
}

impl SiteClient {
    pub fn new(base_url: &str, token: Option<String>) -> Self {
        let http = reqwest::blocking::Client::builder()
            .user_agent(format!(
                "WoWForeverGuilde-Companion/{}",
                env!("CARGO_PKG_VERSION")
            ))
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .expect("client HTTP");
        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            token,
            http,
        }
    }

    pub fn set_token(&mut self, token: Option<String>) {
        self.token = token;
    }

    fn url(&self, path: &str) -> String {
        format!(
            "{}/api/sync/{}",
            self.base_url,
            path.trim_start_matches('/')
        )
    }

    fn authed(&self, req: reqwest::blocking::RequestBuilder) -> reqwest::blocking::RequestBuilder {
        match &self.token {
            Some(token) => req.header("Authorization", format!("Companion {token}")),
            None => req,
        }
    }

    fn error_from(response: reqwest::blocking::Response) -> CoreError {
        let status = response.status().as_u16();
        let message = response
            .json::<ErrorBody>()
            .ok()
            .and_then(|b| {
                b.detail.or_else(|| {
                    b.code.map(|c| match c {
                        serde_json::Value::Array(items) => items
                            .iter()
                            .filter_map(|i| i.as_str())
                            .collect::<Vec<_>>()
                            .join(" "),
                        other => other.to_string(),
                    })
                })
            })
            .unwrap_or_else(|| match status {
                401 => "jeton inconnu ou révoqué : refais l'appairage".to_string(),
                _ => format!("le site a répondu {status}"),
            });
        CoreError::Api { status, message }
    }

    /// Échange le code d'appairage affiché sur le site contre un jeton longue durée.
    pub fn pair(&self, code: &str, device_name: &str) -> Result<PairResponse> {
        let response = self
            .http
            .post(self.url("pair/"))
            .json(&serde_json::json!({ "code": code.trim(), "device_name": device_name }))
            .send()?;
        if response.status().is_success() {
            Ok(response.json()?)
        } else {
            Err(Self::error_from(response))
        }
    }

    /// Envoie un code d'export tel quel. `Err(Duplicate)` si le site l'a déjà reçu.
    pub fn import(&self, code: &str) -> Result<ImportBatch> {
        let response = self
            .authed(self.http.post(self.url("import/")))
            .json(&serde_json::json!({ "code": code }))
            .send()?;
        match response.status().as_u16() {
            200 | 201 => Ok(response.json()?),
            409 => Err(CoreError::Duplicate),
            _ => Err(Self::error_from(response)),
        }
    }

    pub fn status(&self) -> Result<CompanionStatus> {
        let response = self
            .authed(self.http.get(self.url("companion/me/")))
            .send()?;
        if response.status().is_success() {
            Ok(response.json()?)
        } else {
            Err(Self::error_from(response))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use httpmock::prelude::*;

    #[test]
    fn pair_then_import_then_duplicate() {
        let server = MockServer::start();
        server.mock(|when, then| {
            when.method(POST).path("/api/sync/pair/").json_body(serde_json::json!({ "code": "ABC234", "device_name": "PC" }));
            then.status(201).json_body(serde_json::json!({ "token": "tok", "device": { "id": 7, "name": "PC" }, "display_name": "Jordan" }));
        });
        server.mock(|when, then| {
            when.method(POST).path("/api/sync/import/").header("Authorization", "Companion tok").json_body(serde_json::json!({ "code": "WFG1:x" }));
            then.status(201).json_body(serde_json::json!({ "id": 1, "received_at": "2026-12-01T10:00:00Z", "summary": { "applied": 2, "new_recipes": 12 }, "snapshots": [] }));
        });
        server.mock(|when, then| {
            when.method(POST)
                .path("/api/sync/import/")
                .json_body(serde_json::json!({ "code": "WFG1:dup" }));
            then.status(409).json_body(
                serde_json::json!({ "detail": "Ce code a déjà été importé : rien de nouveau." }),
            );
        });
        server.mock(|when, then| {
            when.method(POST).path("/api/sync/import/").json_body(serde_json::json!({ "code": "bad" }));
            then.status(400).json_body(serde_json::json!({ "code": ["Ce texte n'est pas un code d'export de l'addon (il doit commencer par « WFG »)."] }));
        });

        let mut client = SiteClient::new(&server.base_url(), None);
        let paired = client
            .pair(" abc234 ".to_uppercase().as_str(), "PC")
            .unwrap();
        assert_eq!(paired.display_name, "Jordan");
        client.set_token(Some(paired.token));
        let batch = client.import("WFG1:x").unwrap();
        assert_eq!(
            batch.summary.describe(),
            "2 mis à jour, 12 nouvelles recettes"
        );
        assert!(matches!(
            client.import("WFG1:dup"),
            Err(CoreError::Duplicate)
        ));
        match client.import("bad") {
            Err(CoreError::Api {
                status: 400,
                message,
            }) => assert!(message.contains("WFG")),
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn status_unauthorized_is_explicit() {
        let server = MockServer::start();
        server.mock(|when, then| {
            when.method(GET).path("/api/sync/companion/me/");
            then.status(401).body("");
        });
        let client = SiteClient::new(&server.base_url(), Some("old".into()));
        match client.status() {
            Err(CoreError::Api {
                status: 401,
                message,
            }) => assert!(message.contains("appairage")),
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn summary_wording() {
        assert_eq!(Summary::default().describe(), "rien de nouveau");
        assert_eq!(
            Summary {
                created: 1,
                refused: 2,
                ..Default::default()
            }
            .describe(),
            "1 créé, 2 refusés"
        );
    }
}
