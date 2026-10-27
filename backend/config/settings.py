"""
Réglages Django de la plateforme de guilde.

Tout ce qui varie entre environnements vient des variables d'environnement
(cf. deploy/.env.example).
"""

import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Variable d'environnement manquante : {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def database_from_url(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or 5432),
            "CONN_MAX_AGE": 60,
        }
    if parsed.scheme == "sqlite":
        name = parsed.path or ":memory:"
        if name.startswith("//"):
            name = name[1:]
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": name}
    raise RuntimeError(f"DATABASE_URL non reconnue : {url}")


# --- Sécurité et hôtes -----------------------------------------------------

DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key" if DEBUG else None)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Derrière Caddy, c'est le proxy qui termine le TLS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 jours
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # le front lit le cookie pour renvoyer X-CSRFToken

# --- Applications -----------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.accounts",
    "apps.guild",
    "apps.gamedata",
    "apps.characters",
    "apps.polls",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de données --------------------------------------------------------

DATABASES = {
    "default": database_from_url(env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}")),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentification -------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS: list[dict] = []  # pas de mot de passe côté site

# --- Discord ----------------------------------------------------------------

DISCORD_CLIENT_ID = env("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = env("DISCORD_CLIENT_SECRET", "")
DISCORD_BOT_TOKEN = env("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = env("DISCORD_GUILD_ID", "")
DISCORD_ALLOWED_ROLE_IDS = env_list("DISCORD_ALLOWED_ROLE_IDS")
DISCORD_FIRST_GM_ID = env("DISCORD_FIRST_GM_ID", "")
DISCORD_API_BASE = "https://discord.com/api/v10"

# URL publique du site (pour l'URL de retour OAuth) et URL du front (redirection après connexion).
SITE_URL = env("SITE_URL", "http://localhost:8000" if DEBUG else None).rstrip("/")
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173" if DEBUG else SITE_URL).rstrip("/")

# En dev, le front (serveur Vite) est une autre origine que Django : on la déclare de confiance pour le CSRF.
if DEBUG and FRONTEND_URL not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(FRONTEND_URL)

# --- API --------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "WoW Forever — API de guilde",
    "DESCRIPTION": "API privée de la plateforme de guilde.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- Internationalisation ---------------------------------------------------

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# --- Fichiers statiques -----------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Journalisation ---------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
