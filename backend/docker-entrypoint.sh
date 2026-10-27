#!/usr/bin/env sh
set -eu

echo "→ Migrations"
python manage.py migrate --noinput

echo "→ Fichiers statiques"
python manage.py collectstatic --noinput --clear >/dev/null

exec "$@"
