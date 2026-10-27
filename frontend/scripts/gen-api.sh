#!/usr/bin/env sh
# Régénère openapi.json et src/api/schema.d.ts depuis le backend Django.
set -eu
FRONT="$(cd "$(dirname "$0")/.." && pwd)"
BACK="$FRONT/../backend"

cd "$BACK"
DJANGO_SETTINGS_MODULE=config.settings_test uv run python manage.py spectacular \
  --file "$FRONT/openapi.json" --format openapi-json --validate

cd "$FRONT"
npx openapi-typescript openapi.json -o src/api/schema.d.ts
