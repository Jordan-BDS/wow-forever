from rest_framework import serializers

from apps.characters.models import Character
from apps.characters.serializers import OwnerSerializer
from apps.gamedata.index_views import RecipeSerializer
from apps.gamedata.models import Recipe

from .models import CraftRequest, CraftStatus, Materials


class CrafterCharacterSerializer(serializers.ModelSerializer):
    player_class = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    owner = OwnerSerializer(read_only=True)

    class Meta:
        model = Character
        fields = ["id", "name", "player_class", "level", "owner"]
        read_only_fields = fields


class CraftRequestSerializer(serializers.ModelSerializer):
    requester = OwnerSerializer(read_only=True)
    recipe = RecipeSerializer(read_only=True)
    recipe_id = serializers.PrimaryKeyRelatedField(
        source="recipe", queryset=Recipe.objects.all(), write_only=True
    )
    target_character = CrafterCharacterSerializer(read_only=True)
    target_character_id = serializers.PrimaryKeyRelatedField(
        source="target_character",
        queryset=Character.objects.filter(owner__is_active=True),
        write_only=True,
        required=False,
        allow_null=True,
    )
    crafter = CrafterCharacterSerializer(read_only=True)
    status = serializers.ChoiceField(choices=CraftStatus.choices, read_only=True)
    materials = serializers.ChoiceField(choices=Materials.choices, default=Materials.NONE)

    class Meta:
        model = CraftRequest
        fields = [
            "id",
            "requester",
            "recipe",
            "recipe_id",
            "quantity",
            "target_character",
            "target_character_id",
            "materials",
            "note",
            "status",
            "crafter",
            "created_at",
            "updated_at",
            "taken_at",
            "delivered_at",
        ]
        read_only_fields = ["created_at", "updated_at", "taken_at", "delivered_at"]
        extra_kwargs = {"quantity": {"min_value": 1, "max_value": 200}}

    def validate(self, attrs):
        target: Character | None = attrs.get("target_character")
        recipe: Recipe = attrs.get("recipe") or (self.instance.recipe if self.instance else None)
        if target and recipe and not target.known_recipes.filter(recipe=recipe).exists():
            raise serializers.ValidationError(
                {"target_character_id": f"{target.name} ne connaît pas cette recette."}
            )
        return attrs


class TakeSerializer(serializers.Serializer):
    character = serializers.PrimaryKeyRelatedField(queryset=Character.objects.all())
