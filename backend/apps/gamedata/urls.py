from django.urls import path

from .views import GameDataView

urlpatterns = [
    path("gamedata/", GameDataView.as_view(), name="gamedata"),
]
