"""Flux de connexion Discord : redirection, callback, déconnexion."""

import logging
import secrets

from django.conf import settings
from django.contrib.auth import login, logout
from django.http import HttpRequest, HttpResponseRedirect
from django.views.decorators.http import require_GET
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.guild.config import discord_config

from . import discord, services

logger = logging.getLogger(__name__)

STATE_SESSION_KEY = "discord_oauth_state"


def _front_login_error(code: str) -> HttpResponseRedirect:
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}/login?error={code}")


@require_GET
def discord_login(request: HttpRequest) -> HttpResponseRedirect:
    if not discord_config().login_ready:
        return _front_login_error("not_configured")
    state = secrets.token_urlsafe(32)
    request.session[STATE_SESSION_KEY] = state
    return HttpResponseRedirect(discord.authorize_url(state))


@require_GET
def discord_callback(request: HttpRequest) -> HttpResponseRedirect:
    expected_state = request.session.pop(STATE_SESSION_KEY, None)
    if request.GET.get("error"):
        return _front_login_error("discord_denied")
    if not expected_state or request.GET.get("state") != expected_state:
        return _front_login_error("state_mismatch")
    code = request.GET.get("code")
    if not code:
        return _front_login_error("discord_error")

    try:
        user = services.login_from_discord(code)
    except services.AccessDenied as exc:
        return _front_login_error(exc.code)
    except discord.DiscordError:
        logger.exception("Échec de la connexion Discord")
        return _front_login_error("discord_error")

    login(request, user)
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}/")


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
