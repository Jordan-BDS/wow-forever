from django.urls import path

from .index_views import (
    ClassTalentsView,
    EnchantmentListView,
    ItemDetailView,
    ItemSearchView,
    RecipeListView,
)
from .views import GameDataView

urlpatterns = [
    path("gamedata/", GameDataView.as_view(), name="gamedata"),
    path("items/", ItemSearchView.as_view(), name="item-search"),
    path("items/<int:pk>/", ItemDetailView.as_view(), name="item-detail"),
    path("talents/<slug:slug>/", ClassTalentsView.as_view(), name="class-talents"),
    path("enchantments/", EnchantmentListView.as_view(), name="enchantment-list"),
    path("recipes/", RecipeListView.as_view(), name="recipe-list"),
]
