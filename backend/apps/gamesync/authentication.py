"""Authentification du compagnon : en-tête ``Authorization: Companion <jeton>``."""

from rest_framework import authentication, exceptions

from . import services


class CompanionTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Companion"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("Jeton de compagnon mal formé.")
        device = services.device_for_token(header[1].decode(errors="ignore"))
        if device is None:
            raise exceptions.AuthenticationFailed(
                "Jeton de compagnon inconnu ou révoqué : refais l'appairage."
            )
        return device.user, device

    def authenticate_header(self, request):
        return self.keyword
