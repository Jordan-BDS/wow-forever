"""API de consultation de l'index du jeu : objets (autocomplétion), talents, enchantements, recettes."""

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Enchantment, ImportRun, Item, ItemSet, PlayerClass, Recipe, Talent, TalentTree
from .stats import INVENTORY_TYPES, icon_url

MAX_RESULTS = 30


class ItemSetSerializer(serializers.ModelSerializer):
    item_ids = serializers.SerializerMethodField()

    class Meta:
        model = ItemSet
        fields = ["id", "name", "bonuses", "item_ids"]

    def get_item_ids(self, item_set: ItemSet) -> list[int]:
        return list(item_set.items.values_list("id", flat=True))


class ItemSerializer(serializers.ModelSerializer):
    slot = serializers.SerializerMethodField()
    stats = serializers.DictField(child=serializers.IntegerField(), read_only=True)
    icon_url = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            "id",
            "name",
            "name_en",
            "quality",
            "item_level",
            "required_level",
            "inventory_type",
            "slot",
            "class_id",
            "subclass_id",
            "allowable_class",
            "is_unique",
            "item_set",
            "icon",
            "icon_url",
            "stats",
            "description",
            "is_forever",
        ]

    def get_slot(self, item: Item) -> str:
        return INVENTORY_TYPES.get(item.inventory_type, "")

    def get_icon_url(self, item: Item) -> str:
        return icon_url(item.icon)


class ItemDetailSerializer(ItemSerializer):
    item_set = ItemSetSerializer(read_only=True)


class ItemSearchView(ListAPIView):
    """Recherche d'objets : `q` (nom FR ou EN), `slot` (emplacements séparés par des virgules)."""

    serializer_class = ItemSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Début ou fragment du nom (français ou anglais)."),
            OpenApiParameter("slot", str, description="Emplacements acceptés, ex. head ou finger,trinket."),
            OpenApiParameter("equippable", bool, description="Seulement les objets équipables."),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        params = self.request.query_params
        queryset = Item.objects.all()
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(name_en__icontains=query))
        slots = [s for s in params.get("slot", "").split(",") if s]
        if slots:
            types = [t for t, slot in INVENTORY_TYPES.items() if slot in slots]
            queryset = queryset.filter(inventory_type__in=types)
        if params.get("equippable") in ("1", "true"):
            queryset = queryset.filter(inventory_type__gt=0)
        queryset = queryset.order_by("name") if query else queryset.order_by("-item_level", "name")
        return queryset[:MAX_RESULTS]


class ItemDetailView(RetrieveAPIView):
    serializer_class = ItemDetailSerializer
    queryset = Item.objects.select_related("item_set")


class TalentSerializer(serializers.ModelSerializer):
    icon_url = serializers.SerializerMethodField()
    rank_spells = serializers.ListField(child=serializers.IntegerField(), read_only=True)
    max_rank = serializers.IntegerField(read_only=True)

    class Meta:
        model = Talent
        fields = [
            "id",
            "name",
            "icon",
            "icon_url",
            "row",
            "column",
            "rank_spells",
            "max_rank",
            "prerequisite",
            "prerequisite_rank",
        ]

    def get_icon_url(self, talent: Talent) -> str:
        return icon_url(talent.icon)


class TalentTreeSerializer(serializers.ModelSerializer):
    talents = TalentSerializer(many=True, read_only=True)

    class Meta:
        model = TalentTree
        fields = ["id", "name", "background", "order", "talents"]


class ClassTalentsSerializer(serializers.Serializer):
    player_class = serializers.CharField()
    trees = TalentTreeSerializer(many=True)


class ClassTalentsView(APIView):
    """Les trois arbres de talents d'une classe (par slug)."""

    @extend_schema(responses=ClassTalentsSerializer)
    def get(self, request: Request, slug: str) -> Response:
        player_class = PlayerClass.objects.filter(slug=slug).first()
        if player_class is None:
            return Response({"detail": "Classe inconnue."}, status=404)
        trees = TalentTree.objects.filter(player_class=player_class).prefetch_related("talents")
        return Response(ClassTalentsSerializer({"player_class": slug, "trees": trees}).data)


class EnchantmentSerializer(serializers.ModelSerializer):
    icon_url = serializers.SerializerMethodField()

    class Meta:
        model = Enchantment
        fields = [
            "id",
            "name",
            "spell_id",
            "icon",
            "icon_url",
            "stats",
            "slot_mask",
            "equipped_class",
            "equipped_subclass_mask",
            "required_skill",
            "required_skill_rank",
        ]

    def get_icon_url(self, enchantment: Enchantment) -> str:
        return icon_url(enchantment.icon)


class EnchantmentListView(ListAPIView):
    """Enchantements, filtrables par emplacement (`slot`) via le masque d'InventoryType."""

    serializer_class = EnchantmentSerializer

    @extend_schema(parameters=[OpenApiParameter("slot", str), OpenApiParameter("q", str)])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        params = self.request.query_params
        queryset = Enchantment.objects.all()
        if query := params.get("q", "").strip():
            queryset = queryset.filter(name__icontains=query)
        slot = params.get("slot")
        if slot:
            types = [t for t, s in INVENTORY_TYPES.items() if s == slot]
            mask = sum(1 << t for t in types)
            queryset = [e for e in queryset if e.slot_mask == 0 or e.slot_mask & mask]
        return queryset


class CrafterSerializer(serializers.Serializer):
    character_id = serializers.IntegerField()
    name = serializers.CharField()
    player_class = serializers.CharField()
    level = serializers.IntegerField()
    skill = serializers.IntegerField()
    owner_id = serializers.IntegerField()
    owner_name = serializers.CharField()


class RecipeSerializer(serializers.ModelSerializer):
    profession = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    product = ItemSerializer(read_only=True)
    icon_url = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()
    crafters = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = [
            "id",
            "profession",
            "name",
            "icon",
            "icon_url",
            "min_skill",
            "skill_yellow",
            "skill_grey",
            "product",
            "quantity",
            "reagents",
            "acquire_method",
            "source",
            "crafters",
            "is_forever",
        ]

    def get_icon_url(self, recipe: Recipe) -> str:
        return icon_url(recipe.icon)

    @extend_schema_field(CrafterSerializer(many=True))
    def get_crafters(self, recipe: Recipe) -> list[dict]:
        """Personnages actifs qui connaissent la recette, avec leur niveau de compétence dans le métier."""
        rows = []
        for known in recipe.known_by.all():
            character = known.character
            if not character.owner.is_active:
                continue
            skill = next(
                (cp.skill for cp in character.professions.all() if cp.profession_id == recipe.profession_id),
                0,
            )
            rows.append(
                {
                    "character_id": character.pk,
                    "name": character.name,
                    "player_class": character.player_class.slug,
                    "level": character.level,
                    "skill": skill,
                    "owner_id": character.owner_id,
                    "owner_name": character.owner.display_name,
                }
            )
        return sorted(rows, key=lambda r: -r["skill"])

    def get_source(self, recipe: Recipe) -> str:
        # Le client ne dit pas clairement d'où vient une recette : on n'affiche que ce qui est sûr.
        return "Formateur" if recipe.acquire_method == 3 else ""


class RecipeListView(ListAPIView):
    """Recettes : `profession` (slug), `q` (nom de recette ou d'objet produit)."""

    serializer_class = RecipeSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("profession", str),
            OpenApiParameter("q", str),
            OpenApiParameter(
                "known", bool, description="Seulement les recettes connues par au moins un perso."
            ),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        params = self.request.query_params
        queryset = Recipe.objects.select_related(
            "profession", "product", "product__item_set"
        ).prefetch_related(
            "known_by__character__owner",
            "known_by__character__player_class",
            "known_by__character__professions",
        )
        if params.get("known") in ("1", "true"):
            queryset = queryset.filter(known_by__character__owner__is_active=True).distinct()
        if profession := params.get("profession"):
            queryset = queryset.filter(profession__slug=profession)
        if query := params.get("q", "").strip():
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(product__name__icontains=query)
                | Q(product__name_en__icontains=query)
            )
        return queryset[: MAX_RESULTS * 10]


class ImportRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRun
        fields = ["build", "product", "imported_at", "counts"]
