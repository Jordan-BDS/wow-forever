//! Cœur du compagnon WoW Forever Guilde, sans interface : tout ce qui se teste sans fenêtre.
//!
//! - `wowdir` : trouver et valider le dossier du jeu ;
//! - `savedvars` : lire le code d'export écrit par l'addon dans `SavedVariables` ;
//! - `addon` : installer et mettre à jour l'addon embarqué dans l'exécutable ;
//! - `api` : appairage, import, état, auprès du site ;
//! - `sync` : la boucle « fichier changé → code → site », avec l'empreinte anti-doublon ;
//! - `deaths` : lecture des lignes de mort dans le journal de chat (extension du lot 9) ;
//! - `config` : réglages et jeton sur le disque.

pub mod addon;
pub mod api;
pub mod config;
pub mod deaths;
pub mod error;
pub mod savedvars;
pub mod sync;
pub mod wowdir;

pub use error::CoreError;
