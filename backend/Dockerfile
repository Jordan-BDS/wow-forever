FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
# --max-requests : un worker ne rend jamais la mémoire d'une grosse requête ; il est remplacé toutes les 500
# requêtes environ (le serveur n'a que 2 Go), pas les deux en même temps (jitter).
# Deux workers de quatre threads : huit requêtes à la fois au lieu de deux. Une page en lance quatre ou cinq,
# et l'envoi d'un scan de l'hôtel des ventes n'occupe plus la moitié du serveur.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--worker-class", "gthread", "--threads", "4", "--max-requests", "500", "--max-requests-jitter", "100", "--access-logfile", "-"]
