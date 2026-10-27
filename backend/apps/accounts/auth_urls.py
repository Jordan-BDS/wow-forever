from django.urls import path

from . import auth_views
from .views import MeView, MyAvailabilityView

urlpatterns = [
    path("discord/login/", auth_views.discord_login, name="discord-login"),
    path("discord/callback/", auth_views.discord_callback, name="discord-callback"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/availability/", MyAvailabilityView.as_view(), name="me-availability"),
]
