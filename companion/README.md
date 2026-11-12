# Compagnon Manuel Feralas (WoW Forever Guilde)

Application de bureau (Tauri 2) qui installe l'addon dans le dossier du jeu, surveille le fichier `SavedVariables`
qu'il écrit à chaque déconnexion ou `/reload`, et envoie le code d'export au site. Cahier des charges, étape 11.

- `core/` : bibliothèque Rust sans interface, testée par `cargo test` (dossier WoW, SavedVariables, addon embarqué,
  API du site, boucle de synchronisation, complétion depuis le site).
- `app/` : interface React + `src-tauri/` (fenêtre, barre des tâches, surveillance de fichier, mise à jour).

Dans l'autre sens, au lancement et jeu fermé, le compagnon recopie dans `SavedVariables` l'état fusionné que le site
a de chaque personnage (toutes installations), avec une marque `seed` pour que le site ne compte rien deux fois :
une réinstallation ou un second PC ne repart jamais de zéro. Le fichier est lu et réécrit par `core/src/luatable.rs`.

Hôtel des ventes (`core/src/auctions.rs`) : si l'addon tiers NaowhForever est installé, son dernier scan complet
(`ahPrices` dans `SavedVariables/NaowhForever.lua`) part au site à chaque nouveau scan, pour qui en a le droit
(`/api/sync/auctions/rights/`, le GM pour l'instant). Chez les autres, le fichier n'est pas lu et
rien n'est envoyé ; un échec ici ne touche jamais à l'envoi des personnages. Le site en tire la page `/hv`.

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
`app/package.json`, `app/src-tauri/Cargo.toml`, `app/src-tauri/tauri.conf.json`, `core/Cargo.toml`, le tag, et côté
addon dans `WoWForeverGuilde.toc` (`## Version`) et `Core.lua` (`CODE_VERSION`, qu'un test garde égale au `.toc`).

## Mise à jour automatique

Au lancement, toutes les 10 minutes et après chaque synchronisation (pas plus d'une fois toutes les 2 minutes), le
compagnon lit `latest.json` de la dernière release GitHub (`plugins.updater.endpoints`) ;
s'il existe une version plus récente, il la télécharge, l'installe et redémarre. L'addon embarqué suit, puisqu'il
est compilé dans l'exécutable. Exception : la 0.1.0 ne contenait pas cette vérification, il faut la remplacer à la
main par un installeur plus récent. L'adresse du site est `https://wow.koj.dev` par défaut, modifiable dans la fenêtre.
