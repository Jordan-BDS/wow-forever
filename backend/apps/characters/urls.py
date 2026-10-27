from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .recipe_views import KnownRecipesView
from .sheet_views import EquipmentSetViewSet, TalentBuildViewSet
from .views import CharacterViewSet

router = DefaultRouter()
router.register("characters", CharacterViewSet, basename="character")

sheet = DefaultRouter()
sheet.register("equipment-sets", EquipmentSetViewSet, basename="equipment-set")
sheet.register("talent-builds", TalentBuildViewSet, basename="talent-build")

urlpatterns = [
    *router.urls,
    path("characters/<int:pk>/recipes/", KnownRecipesView.as_view(), name="character-recipes"),
    path("characters/<int:character_pk>/", include(sheet.urls)),
]
