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
# Django lit backend/.env tout seul ; pour PostgreSQL ajouter DATABASE_URL=postgres://wow:wow@localhost:5432/wow
uv run python manage.py migrate
uv run python manage.py seed_gamedata # classes, races, spés, métiers (rejouable)
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
| backend | `uv run python manage.py seed_gamedata` | recharge les données de référence sans toucher aux ajouts manuels |
| backend | `uv run python manage.py runbot` | lance le bot Discord (outbox, rappels, commandes slash, révocation) |
| backend | `uv run python manage.py import_gamedata` | télécharge les tables du client WoW Forever (wago.tools) et importe objets, sets, enchantements, talents, recettes (~2 min, rejouable) |

En production : `docker compose exec web python manage.py import_gamedata` après la première mise en ligne, puis
à chaque patch du jeu. Les ajouts manuels faits dans l'admin (lignes « gérées à la main ») sont conservés.
| frontend | `npm test` / `npm run lint` / `npm run format` | tests, lint, format |
| frontend | `npm run gen:api` | régénère `openapi.json` et `src/api/schema.d.ts` depuis le backend |

L'API est documentée sur `http://localhost:8000/api/docs/` (Swagger).

Sans application Discord, on peut tester en créant un superutilisateur puis en se connectant sur
`/admin/login/` : la session est reconnue par le site.

## Application Discord

Dans le [Discord Developer Portal](https://discord.com/developers/applications), créer une application :

1. **OAuth2** : récupérer *Client ID* et *Client Secret*, ajouter l'URL de retour dans *Redirects*.
2. **Bot** : créer le bot, copier son token, activer l'intent privilégié *Server Members*. Inviter le bot sur le
   serveur avec les scopes `bot` et `applications.commands`, et les permissions *Voir les salons* et *Envoyer des
   messages*. Le GM renseigne ensuite l'ID du salon des annonces dans les paramètres du site.
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

### Derrière un nginx déjà présent sur le VPS

Si nginx occupe déjà les ports 80 et 443, Caddy reste dans Compose mais écoute en HTTP sur `127.0.0.1:8080`
et nginx termine le TLS :

```sh
cd /opt/wow-forever/deploy
cp .env.example .env && $EDITOR .env           # SITE_DOMAIN n'est pas utilisé dans ce mode
docker compose -f docker-compose.yml -f docker-compose.nginx.yml up -d --build
sudo cp nginx/wow.koj.dev.conf /etc/nginx/sites-available/wow.koj.dev   # adapter le domaine
sudo ln -s /etc/nginx/sites-available/wow.koj.dev /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d wow.koj.dev
```

Dans `.env`, mettre `SITE_URL`, `DJANGO_ALLOWED_HOSTS` et `DJANGO_CSRF_TRUSTED_ORIGINS` sur le domaine public en
`https`. Pour les mises à jour, garder les deux fichiers `-f` dans la commande.

### Première mise en ligne

1. `docker compose … exec web python manage.py import_gamedata` (objets, talents, recettes ; ~2 min).
2. Ajouter `https://<domaine>/api/auth/discord/callback/` dans les Redirects de l'application Discord.
3. Se connecter avec Discord : le premier GM est promu, puis Guilde › Paramètres pour vérifier la configuration.
   Les réglages Discord saisis en local se transfèrent avec
   `python manage.py dumpdata guild.guildsettings > guild.json` puis `loaddata` dans le conteneur.
