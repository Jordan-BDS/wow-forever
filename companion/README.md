# Compagnon WoW Forever Guilde

Application de bureau (Tauri 2) qui installe l'addon dans le dossier du jeu, surveille le fichier `SavedVariables`
qu'il écrit à chaque déconnexion ou `/reload`, et envoie le code d'export au site. Cahier des charges, étape 11.

- `core/` : bibliothèque Rust sans interface, testée par `cargo test` (dossier WoW, SavedVariables, addon embarqué,
  API du site, boucle de synchronisation, journal de chat).
- `app/` : interface React + `src-tauri/` (fenêtre, barre des tâches, surveillance de fichier, mise à jour).

## Développer

Prérequis : Rust (rustup), Node 20, et sous Linux les bibliothèques Tauri
(`libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev libxdo-dev libssl-dev patchelf`).

```sh
cd companion/core && cargo test               # le cœur, sans interface
cd companion/app && npm install && npm run tauri dev   # l'application, pointée sur le site réglé dans la fenêtre
```

## Publier

Un tag `companion-vX.Y.Z` déclenche `.github/workflows/companion-release.yml` : construction Windows (NSIS) et
macOS (universel), artefacts de mise à jour signés, zip de l'addon seul, release GitHub. Le site lit la dernière
release pour afficher les liens de téléchargement (`/api/sync/release/`).

Avant la première release : générer la paire de clés de mise à jour (`npm run tauri signer generate`), mettre la clé
publique dans `app/src-tauri/tauri.conf.json` (`plugins.updater.pubkey`) et la clé privée dans les secrets GitHub
`TAURI_SIGNING_PRIVATE_KEY` / `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. Le même numéro de version doit figurer dans
`app/package.json`, `app/src-tauri/Cargo.toml`, `app/src-tauri/tauri.conf.json` et le tag.
