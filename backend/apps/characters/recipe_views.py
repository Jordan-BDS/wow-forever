"""Recettes connues par un personnage : liste, remplacement, cochage automatique des recettes de formateur."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.gamedata.models import Recipe

from .models import Character, KnownRecipe


class KnownRecipesSerializer(serializers.Serializer):
    recipes = serializers.ListField(child=serializers.IntegerField())


class KnownRecipesView(APIView):
    """GET : IDs des recettes connues. PUT : remplace la liste. POST : coche les recettes de formateur."""

    def _character(self, request: Request, pk: int, write: bool = False) -> Character:
        character = get_object_or_404(Character.objects.prefetch_related("professions__profession"), pk=pk)
        if write and character.owner_id != request.user.pk and not request.user.is_officer_or_above:
            raise PermissionDenied("Tu ne peux modifier que tes propres personnages.")
        return character

    @extend_schema(responses=KnownRecipesSerializer)
    def get(self, request: Request, pk: int) -> Response:
        character = self._character(request, pk)
        return Response({"recipes": list(character.known_recipes.values_list("recipe_id", flat=True))})

    @extend_schema(request=KnownRecipesSerializer, responses=KnownRecipesSerializer)
    def put(self, request: Request, pk: int) -> Response:
        character = self._character(request, pk, write=True)
        serializer = KnownRecipesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        professions = {cp.profession_id for cp in character.professions.all()}
        wanted = set(serializer.validated_data["recipes"])
        allowed = set(
            Recipe.objects.filter(id__in=wanted, profession_id__in=professions).values_list("id", flat=True)
        )
        if wanted - allowed:
            raise serializers.ValidationError(
                {"recipes": "Recette inconnue ou qui ne correspond pas aux métiers du personnage."}
            )
        with transaction.atomic():
            character.known_recipes.exclude(recipe_id__in=allowed).delete()
            existing = set(character.known_recipes.values_list("recipe_id", flat=True))
            KnownRecipe.objects.bulk_create(
                [KnownRecipe(character=character, recipe_id=rid) for rid in allowed - existing]
            )
        return Response({"recipes": sorted(allowed)})

    @extend_schema(request=None, responses=KnownRecipesSerializer)
    def post(self, request: Request, pk: int) -> Response:
        """Coche toutes les recettes accessibles au niveau de compétence de chaque métier (à élaguer ensuite)."""
        character = self._character(request, pk, write=True)
        added = 0
        with transaction.atomic():
            for cp in character.professions.all():
                trainer_recipes = Recipe.objects.filter(
                    profession_id=cp.profession_id, min_skill__lte=cp.skill
                ).values_list("id", flat=True)
                existing = set(character.known_recipes.values_list("recipe_id", flat=True))
                new = [
                    KnownRecipe(character=character, recipe_id=rid)
                    for rid in trainer_recipes
                    if rid not in existing
                ]
                KnownRecipe.objects.bulk_create(new)
                added += len(new)
        return Response(
            {"recipes": list(character.known_recipes.values_list("recipe_id", flat=True)), "added": added}
        )
