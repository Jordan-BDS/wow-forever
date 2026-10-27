"""Réglages pour la suite de tests : valeurs par défaut pour toutes les variables d'environnement."""

import os

os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key")
os.environ.setdefault("DISCORD_CLIENT_ID", "client-id")
os.environ.setdefault("DISCORD_CLIENT_SECRET", "client-secret")
os.environ.setdefault("DISCORD_BOT_TOKEN", "bot-token")
os.environ.setdefault("DISCORD_GUILD_ID", "999")
os.environ.setdefault("DISCORD_ALLOWED_ROLE_IDS", "role-member,role-officer")
os.environ.setdefault("DISCORD_FIRST_GM_ID", "42")
os.environ.setdefault("SITE_URL", "http://testserver")
os.environ.setdefault("FRONTEND_URL", "http://front.test")

from .settings import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
