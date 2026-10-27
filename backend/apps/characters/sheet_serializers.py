"""Sérialiseurs de la fiche de personnage : sets d'équipement, builds de talents, stats."""

from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.gamedata.index_views import EnchantmentSerializer, ItemSerializer
from apps.gamedata.models import Enchantment, Item

from . import equipment, talent_rules
from .models import Character, EquipmentSet, EquipmentSlot, TalentBuild


class SlotSerializer(serializers.Serializer):
    slot = serializers.ChoiceField(choices=equipment.SLOTS)
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all(), allow_null=True, required=False)
    enchantment = serializers.PrimaryKeyRelatedField(
        queryset=Enchantment.objects.all(), allow_null=True, required=False
    )


class SlotReadSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    enchantment = EnchantmentSerializer(read_only=True)
    projected = serializers.SerializerMethodField()
    error = serializers.SerializerMethodField()

    class Meta:
        model = EquipmentSlot
        fields = ["slot", "item", "enchantment", "projected", "error"]

    def get_projected(self, slot: EquipmentSlot) -> bool:
        level = self.context.get("level", 60)
        return bool(slot.item and slot.item.required_level > level)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_error(self, slot: EquipmentSlot) -> str | None:
        """Pièce devenue non portable (changement de classe, par exemple) : à vider ou remplacer."""
        class_slug = self.context.get("class_slug")
        if not slot.item or not class_slug:
            return None
        return equipment.item_error(slot.item, slot.slot, class_slug)


class EquipmentSetSerializer(serializers.ModelSerializer):
    slots = SlotReadSerializer(many=True, read_only=True)

    class Meta:
        model = EquipmentSet
        fields = ["id", "character", "name", "is_primary", "slots", "created_at", "updated_at"]
        read_only_fields = ["character", "is_primary", "created_at", "updated_at"]
        extra_kwargs = {"name": {"min_length": 1}}

    def to_representation(self, instance):
        self.context.setdefault("level", instance.character.level)
        self.context.setdefault("class_slug", instance.character.player_class.slug)
        return super().to_representation(instance)


def validate_slots(character: Character, payload: list[dict]) -> dict[str, dict]:
    """Valide une liste d'emplacements et renvoie {slot: {item, enchantment}} ou lève ValidationError."""
    errors: dict[str, str] = {}
    cleaned: dict[str, dict] = {}
    class_slug = character.player_class.slug
    for entry in payload:
        slot, item, enchantment = entry["slot"], entry.get("item"), entry.get("enchantment")
        if slot in cleaned:
            errors[slot] = "Emplacement en double."
            continue
        if item is not None and (error := equipment.item_error(item, slot, class_slug)):
            errors[slot] = error
            continue
        if enchantment is not None:
            if item is None:
                enchantment = None
            elif error := equipment.enchantment_error(enchantment, item):
                errors[slot] = error
                continue
        cleaned[slot] = {"item": item, "enchantment": enchantment}
    errors.update(equipment.set_errors({slot: v["item"] for slot, v in cleaned.items()}))
    if errors:
        raise serializers.ValidationError(errors)
    return cleaned


class SlotsUpdateSerializer(serializers.Serializer):
    """PUT : remplace tous les emplacements du set (ceux absents sont vidés)."""

    slots = SlotSerializer(many=True)

    @transaction.atomic
    def save(self, equipment_set: EquipmentSet) -> EquipmentSet:
        cleaned = validate_slots(equipment_set.character, self.validated_data["slots"])
        equipment_set.slots.all().delete()
        EquipmentSlot.objects.bulk_create(
            [
                EquipmentSlot(
                    equipment_set=equipment_set, slot=slot, item=v["item"], enchantment=v["enchantment"]
                )
                for slot, v in cleaned.items()
                if v["item"] is not None
            ]
        )
        equipment_set.save(update_fields=["updated_at"])
        return equipment_set


class TalentBuildSerializer(serializers.ModelSerializer):
    points = serializers.ListField(child=serializers.IntegerField(), required=False)
    acquired = serializers.SerializerMethodField()
    tree_points = serializers.SerializerMethodField()

    class Meta:
        model = TalentBuild
        fields = [
            "id",
            "character",
            "name",
            "is_active",
            "points",
            "acquired",
            "tree_points",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["character", "is_active", "created_at", "updated_at"]
        extra_kwargs = {"name": {"min_length": 1}}

    def validate_points(self, value: list[int]) -> list[int]:
        character: Character = self.context["character"]
        if error := talent_rules.validate_order(value, character.player_class.slug):
            raise serializers.ValidationError(error)
        return value

    def get_acquired(self, build: TalentBuild) -> int:
        return min(len(build.points), talent_rules.acquired_points(build.character.level))

    def get_tree_points(self, build: TalentBuild) -> dict[str, int]:
        from apps.gamedata.models import Talent

        acquired = build.points[: talent_rules.acquired_points(build.character.level)]
        counts: dict[str, int] = {}
        trees = {
            t.id: t.tree_id for t in Talent.objects.filter(id__in=set(build.points)).only("id", "tree_id")
        }
        for talent_id in acquired:
            key = str(trees.get(talent_id, 0))
            counts[key] = counts.get(key, 0) + 1
        return counts


class SlotPatchSerializer(SlotSerializer):
    """PATCH d'un seul emplacement : seule cette pièce est validée, plus les contrôles croisés."""

    @transaction.atomic
    def save(self, equipment_set: EquipmentSet) -> EquipmentSet:
        data = self.validated_data
        slot, item, enchantment = data["slot"], data.get("item"), data.get("enchantment")
        class_slug = equipment_set.character.player_class.slug
        errors: dict[str, str] = {}
        if item is not None:
            if (
                (error := equipment.item_error(item, slot, class_slug))
                or enchantment is not None
                and (error := equipment.enchantment_error(enchantment, item))
            ):
                errors[slot] = error
        else:
            enchantment = None
        if not errors:
            others = {s.slot: s.item for s in equipment_set.slots.exclude(slot=slot)}
            cross = equipment.set_errors({**others, slot: item})
            if slot in cross:
                errors[slot] = cross[slot]
            else:
                errors.update(cross)
        if errors:
            raise serializers.ValidationError(errors)
        if item is None:
            equipment_set.slots.filter(slot=slot).delete()
        else:
            EquipmentSlot.objects.update_or_create(
                equipment_set=equipment_set, slot=slot, defaults={"item": item, "enchantment": enchantment}
            )
        equipment_set.save(update_fields=["updated_at"])
        return equipment_set
