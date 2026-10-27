# Déploiement Docker sur le VPS, depuis la racine du dépôt.
# Usage : make deploy            (derrière le nginx hôte, cas du VPS)
#         make deploy MODE=caddy (Caddy seul, HTTPS automatique sur SITE_DOMAIN)
MODE ?= nginx

# Nom de projet Compose. Historiquement la stack a été lancée avec `cd deploy && docker compose up`,
# donc Compose l'a nommée « deploy » (nom du dossier). On garde ce nom : avec un autre, Compose
# monterait une stack parallèle sur un volume Postgres vide au lieu de mettre à jour l'existante.
PROJECT ?= deploy

COMPOSE := docker compose -p $(PROJECT) --env-file deploy/.env -f deploy/docker-compose.yml
ifeq ($(MODE),nginx)
COMPOSE += -f deploy/docker-compose.nginx.yml
endif

.PHONY: help build up down deploy update restart logs ps migrate shell dbshell import-gamedata backup

help:             ## Liste des commandes
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{ printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 }'

build:            ## Build les images
	$(COMPOSE) build

up:               ## Démarre la stack
	$(COMPOSE) up -d

deploy:           ## Build + (re)démarre (migrations et statiques au démarrage de web)
	$(COMPOSE) up -d --build

update:           ## git pull puis deploy
	git pull --ff-only
	$(MAKE) deploy

down:             ## Arrête la stack (les volumes restent)
	$(COMPOSE) down

restart:          ## Redémarre web et le bot
	$(COMPOSE) restart web bot

logs:             ## Logs en continu
	$(COMPOSE) logs -f --tail=120

ps:               ## État des services
	$(COMPOSE) ps

migrate:          ## Lance les migrations
	$(COMPOSE) exec web python manage.py migrate --noinput

shell:            ## Shell Django
	$(COMPOSE) exec web python manage.py shell

dbshell:          ## psql sur la base
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

import-gamedata:  ## Importe objets, talents, recettes depuis le client du jeu (~2 min)
	$(COMPOSE) exec web python manage.py import_gamedata

backup:           ## Dump PostgreSQL dans deploy/backups/
	deploy/backup.sh
