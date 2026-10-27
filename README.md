# WoW Forever — plateforme de guilde

Petit site privé pour la guilde sur *World of Warcraft: Forever* : qui joue quoi, qui a quels métiers,
agenda des sorties. Le cahier des charges complet est dans [`docs/cahier-des-charges.md`](docs/cahier-des-charges.md).

```
backend/    Django 5.2 + DRF (API, admin, bientôt le bot Discord)
frontend/   Vite + React + TypeScript + Tailwind
deploy/     Docker Compose, Caddyfile, sauvegardes
docs/       cahier des charges
```

## Développement local

Prérequis : [uv](https://docs.astral.sh/uv/), Node 20.19+ (ou 22), Docker.

```sh
# 1. PostgreSQL (facultatif : sans DATABASE_URL, Django utilise un SQLite local)
docker compose -f deploy/compose.dev.yml up -d

# 2. Backend
cd backend
cp ../deploy/.env.example .env      # puis remplir la partie Discord, mettre DJANGO_DEBUG=true
export $(grep -v '^#' .env | xargs)  # ou utiliser direnv
export DATABASE_URL=postgres://wow:wow@localhost:5432/wow
uv run python manage.py migrate
uv run python manage.py runserver     # http://localhost:8000

# 3. Frontend (dans un autre terminal)
cd frontend
npm install
npm run dev                           # http://localhost:5173, proxy /api → :8000
```

En développement, `SITE_URL` vaut `http://localhost:8000` et `FRONTEND_URL` vaut `http://localhost:5173` :
l'URL de retour OAuth à déclarer côté Discord est donc `http://localhost:8000/api/auth/discord/callback/`.

### Commandes utiles

| Où | Commande | Rôle |
|---|---|---|
| backend | `uv run pytest` | tests |
| backend | `uv run ruff check . && uv run ruff format .` | lint + format |
| backend | `uv run python manage.py createsuperuser` | accès à `/admin/` (demande un ID Discord) |
| frontend | `npm test` / `npm run lint` / `npm run format` | tests, lint, format |
| frontend | `npm run gen:api` | régénère `openapi.json` et `src/api/schema.d.ts` depuis le backend |

L'API est documentée sur `http://localhost:8000/api/docs/` (Swagger).

## Application Discord

Dans le [Discord Developer Portal](https://discord.com/developers/applications), créer une application :

1. **OAuth2** : récupérer *Client ID* et *Client Secret*, ajouter l'URL de retour dans *Redirects*.
2. **Bot** : créer le bot, copier son token. Inviter le bot sur le serveur avec le scope `bot`
   (aucune permission particulière n'est nécessaire au lot 0 ; l'intent *Server Members* viendra avec le lot 3).
3. Activer le *mode développeur* dans Discord pour copier l'ID du serveur, des rôles autorisés et du premier GM.

Les variables à remplir sont décrites dans [`deploy/.env.example`](deploy/.env.example).

## Déploiement sur le VPS

```sh
git clone <dépôt> /opt/wow-forever && cd /opt/wow-forever/deploy
cp .env.example .env && $EDITOR .env    # domaine, mots de passe, Discord
docker compose up -d --build
```

Caddy obtient le certificat HTTPS tout seul (le domaine doit pointer sur le VPS, ports 80 et 443 ouverts).
Mises à jour : `git pull && docker compose up -d --build`. Sauvegardes : `deploy/backup.sh` dans la crontab.
