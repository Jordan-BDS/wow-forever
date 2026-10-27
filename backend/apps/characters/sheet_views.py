"""Vues de la fiche de personnage : sets d'équipement, stats, builds de talents."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from apps.stats import engine

from . import talent_rules
from .models import Character, EquipmentSet, EquipmentSlot, TalentBuild
from .sheet_serializers import (
    EquipmentSetSerializer,
    SlotPatchSerializer,
    SlotsUpdateSerializer,
    TalentBuildSerializer,
    validate_slots,
)


class StatsSerializer(serializers.Serializer):
    totals = serializers.DictField(child=serializers.IntegerField())
    breakdown = serializers.DictField(child=serializers.DictField(child=serializers.IntegerField()))
    active_set_bonuses = serializers.ListField(child=serializers.DictField())
    inactive_set_bonuses = serializers.ListField(child=serializers.DictField())
    projected_slots = serializers.ListField(child=serializers.CharField())


def stats_payload(character: Character, slots: list[EquipmentSlot | dict]) -> dict:
    inputs = []
    for slot in slots:
        item = slot["item"] if isinstance(slot, dict) else slot.item
        enchantment = slot["enchantment"] if isinstance(slot, dict) else slot.enchantment
        name = slot["slot"] if isinstance(slot, dict) else slot.slot
        projected = bool(item and item.required_level > character.level)
        inputs.append(engine.SlotInput(name, item, enchantment, projected))
    result = engine.compute(inputs)
    return StatsSerializer(result).data


class CharacterSheetMixin:
    permission_classes = [permissions.IsAuthenticated]

    def get_character(self) -> Character:
        character = get_object_or_404(
            Character.objects.select_related("player_class", "owner"), pk=self.kwargs["character_pk"]
        )
        self.character = character
        return character

    def check_write(self, character: Character) -> None:
        user = self.request.user
        if character.owner_id != user.pk and not user.is_officer_or_above:
            raise PermissionDenied("Tu ne peux modifier que tes propres personnages.")


class EquipmentSetViewSet(CharacterSheetMixin, viewsets.ModelViewSet):
    """Sets d'équipement d'un personnage (/api/characters/{id}/equipment-sets/)."""

    serializer_class = EquipmentSetSerializer

    def get_queryset(self):
        character = self.get_character()
        return (
            EquipmentSet.objects.filter(character=character)
            .prefetch_related("slots__item__item_set", "slots__enchantment")
            .order_by("-is_primary", "created_at")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if "character_pk" in self.kwargs:
            character = getattr(self, "character", None) or self.get_character()
            context["level"] = character.level
            context["class_slug"] = character.player_class.slug
        return context

    def perform_create(self, serializer):
        character = self.get_character()
        self.check_write(character)
        is_primary = not character.equipment_sets.exists()
        serializer.save(character=character, is_primary=is_primary)

    def perform_update(self, serializer):
        self.check_write(serializer.instance.character)
        serializer.save()

    def perform_destroy(self, instance: EquipmentSet):
        self.check_write(instance.character)
        character = instance.character
        instance.delete()
        if not character.equipment_sets.filter(is_primary=True).exists():
            first = character.equipment_sets.order_by("created_at").first()
            if first:
                first.is_primary = True
                first.save(update_fields=["is_primary"])

    @extend_schema(request=SlotsUpdateSerializer, responses=EquipmentSetSerializer)
    @action(detail=True, methods=["put"])
    def slots(self, request: Request, character_pk=None, pk=None) -> Response:
        equipment_set = self.get_object()
        self.check_write(equipment_set.character)
        serializer = SlotsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(equipment_set)
        return Response(self.get_serializer(self.get_queryset().get(pk=equipment_set.pk)).data)

    @extend_schema(request=SlotPatchSerializer, responses=EquipmentSetSerializer)
    @action(detail=True, methods=["patch"], url_path="slot")
    def slot(self, request: Request, character_pk=None, pk=None) -> Response:
        """Modifie ou vide un seul emplacement sans revalider les autres pièces."""
        equipment_set = self.get_object()
        self.check_write(equipment_set.character)
        serializer = SlotPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(equipment_set)
        return Response(self.get_serializer(self.get_queryset().get(pk=equipment_set.pk)).data)

    @extend_schema(request=None, responses=EquipmentSetSerializer)
    @action(detail=True, methods=["post"], url_path="set-primary")
    def set_primary(self, request: Request, character_pk=None, pk=None) -> Response:
        equipment_set = self.get_object()
        self.check_write(equipment_set.character)
        with transaction.atomic():
            EquipmentSet.objects.filter(character=equipment_set.character, is_primary=True).update(
                is_primary=False
            )
            equipment_set.is_primary = True
            equipment_set.save(update_fields=["is_primary"])
        return Response(self.get_serializer(equipment_set).data)

    @extend_schema(request=None, responses={201: EquipmentSetSerializer})
    @action(detail=True, methods=["post"])
    def duplicate(self, request: Request, character_pk=None, pk=None) -> Response:
        source = self.get_object()
        self.check_write(source.character)
        with transaction.atomic():
            copy = EquipmentSet.objects.create(character=source.character, name=f"{source.name} (copie)"[:40])
            EquipmentSlot.objects.bulk_create(
                [
                    EquipmentSlot(equipment_set=copy, slot=s.slot, item=s.item, enchantment=s.enchantment)
                    for s in source.slots.all()
                ]
            )
        return Response(
            self.get_serializer(self.get_queryset().get(pk=copy.pk)).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(responses=StatsSerializer)
    @action(detail=True, methods=["get"])
    def stats(self, request: Request, character_pk=None, pk=None) -> Response:
        equipment_set = self.get_object()
        return Response(stats_payload(equipment_set.character, list(equipment_set.slots.all())))

    @extend_schema(request=SlotsUpdateSerializer, responses=StatsSerializer)
    @action(detail=False, methods=["post"])
    def preview(self, request: Request, character_pk=None) -> Response:
        """Stats d'une liste d'emplacements sans rien enregistrer."""
        character = self.get_character()
        serializer = SlotsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cleaned = validate_slots(character, serializer.validated_data["slots"])
        slots = [{"slot": slot, **values} for slot, values in cleaned.items()]
        return Response(stats_payload(character, slots))


class TalentBuildViewSet(CharacterSheetMixin, viewsets.ModelViewSet):
    """Builds de talents d'un personnage (/api/characters/{id}/talent-builds/)."""

    serializer_class = TalentBuildSerializer

    def get_queryset(self):
        return TalentBuild.objects.filter(character=self.get_character()).select_related("character")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if "character_pk" in self.kwargs:
            context["character"] = getattr(self, "character", None) or self.get_character()
        return context

    def perform_create(self, serializer):
        character = self.get_character()
        self.check_write(character)
        is_active = not character.talent_builds.exists()
        build = serializer.save(character=character, is_active=is_active)
        if is_active:
            sync_specialization(character, build)

    def perform_update(self, serializer):
        self.check_write(serializer.instance.character)
        build = serializer.save()
        if build.is_active:
            sync_specialization(build.character, build)

    def perform_destroy(self, instance: TalentBuild):
        self.check_write(instance.character)
        character = instance.character
        instance.delete()
        if not character.talent_builds.filter(is_active=True).exists():
            first = character.talent_builds.order_by("created_at").first()
            if first:
                first.is_active = True
                first.save(update_fields=["is_active"])
                sync_specialization(character, first)

    @extend_schema(request=None, responses=TalentBuildSerializer)
    @action(detail=True, methods=["post"])
    def activate(self, request: Request, character_pk=None, pk=None) -> Response:
        build = self.get_object()
        self.check_write(build.character)
        with transaction.atomic():
            TalentBuild.objects.filter(character=build.character, is_active=True).update(is_active=False)
            build.is_active = True
            build.save(update_fields=["is_active"])
            sync_specialization(build.character, build)
        return Response(self.get_serializer(build).data)


def sync_specialization(character: Character, build: TalentBuild) -> None:
    """La spécialisation affichée suit l'arbre le plus investi en points acquis du build actif."""
    acquired = build.points[: talent_rules.acquired_points(character.level)]
    spec = talent_rules.specialization_for(talent_rules.dominant_tree(acquired))
    if spec and character.specialization_id != spec.pk:
        character.specialization = spec
        character.save(update_fields=["specialization", "updated_at"])
