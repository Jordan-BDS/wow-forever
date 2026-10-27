#!/usr/bin/env sh
set -eu

echo "→ Migrations"
python manage.py migrate --noinput

echo "→ Données de référence du jeu"
python manage.py seed_gamedata

echo "→ Fichiers statiques"
python manage.py collectstatic --noinput --clear >/dev/null

exec "$@"
