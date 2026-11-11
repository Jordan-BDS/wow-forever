//! Cœur du compagnon WoW Forever Guilde, sans interface : tout ce qui se teste sans fenêtre.
//!
//! - `wowdir` : trouver et valider le dossier du jeu ;
//! - `savedvars` : lire le code d'export écrit par l'addon dans `SavedVariables` ;
//! - `addon` : installer et mettre à jour l'addon embarqué dans l'exécutable ;
//! - `api` : appairage, import, état, auprès du site ;
//! - `sync` : la boucle « fichier changé → code → site », avec l'empreinte anti-doublon, et le sens inverse
//!   « site → fichier » au lancement (complétion, jeu fermé) ;
//! - `luatable` et `seed` : lire et réécrire le fichier `SavedVariables` pour y recopier l'état du site ;
//! - `auctions` : envoyer les scans de l'hôtel des ventes lus dans le fichier de l'addon NaowhForever (GM) ;
//! - `config` : réglages et jeton sur le disque.

pub mod addon;
pub mod api;
pub mod auctions;
pub mod config;
pub mod error;
pub mod luatable;
pub mod savedvars;
pub mod seed;
pub mod sync;
pub mod wowdir;

pub use error::CoreError;
