from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import User
from apps.gamedata.models import (
    PlayerClass,
    Profession,
    ProfessionKind,
    ProfessionSpecialization,
    Race,
    Role,
    Specialization,
)
from apps.guild.models import GuildSettings

from . import services
from .models import Character, CharacterProfession


class OwnerSerializer(serializers.ModelSerializer):
    avatar_url = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "display_name", "avatar_url"]
        read_only_fields = fields


class CharacterProfessionSerializer(serializers.ModelSerializer):
    profession = serializers.SlugRelatedField(slug_field="slug", queryset=Profession.objects.all())
    specialization = serializers.SlugRelatedField(
        slug_field="slug", queryset=ProfessionSpecialization.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = CharacterProfession
        fields = ["profession", "skill", "specialization"]
        extra_kwargs = {"skill": {"min_value": 1, "max_value": Profession.MAX_SKILL}}

    def validate(self, attrs):
        spec = attrs.get("specialization")
        if spec and spec.profession_id != attrs["profession"].pk:
            raise serializers.ValidationError(
                {"specialization": f"« {spec.name} » n'est pas une spécialisation de ce métier."}
            )
        return attrs


class CharacterSerializer(serializers.ModelSerializer):
    owner = OwnerSerializer(read_only=True)
    owner_id = serializers.PrimaryKeyRelatedField(
        source="owner",
        queryset=User.objects.filter(is_active=True),
        write_only=True,
        required=False,
        help_text="Officiers seulement : créer le perso pour un autre membre.",
    )
    player_class = serializers.SlugRelatedField(slug_field="slug", queryset=PlayerClass.objects.all())
    race = serializers.SlugRelatedField(slug_field="slug", queryset=Race.objects.all())
    specialization = serializers.SlugRelatedField(
        slug_field="slug", queryset=Specialization.objects.all(), allow_null=True, required=False
    )
    professions = CharacterProfessionSerializer(many=True, required=False)

    class Meta:
        model = Character
        fields = [
            "id",
            "owner",
            "owner_id",
            "name",
            "player_class",
            "race",
            "level",
            "main_role",
            "off_role",
            "specialization",
            "is_main",
            "note",
            "professions",
            "source",
            "external_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["source", "external_id", "created_at", "updated_at"]
        # Pas de validateur unique_together automatique : la contrainte « un seul main par joueur » est
        # conditionnelle (gérée par services.set_main) et forcerait owner_id à être obligatoire.
        validators: list = []
        extra_kwargs = {
            "level": {"min_value": 1, "max_value": Character.MAX_LEVEL},
            "name": {"min_length": 2},
        }

    # --- validations ---------------------------------------------------------

    def validate_name(self, value: str) -> str:
        value = value.strip()
        duplicates = Character.objects.filter(name__iexact=value)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("Un personnage porte déjà ce nom dans la guilde.")
        return value

    def validate_professions(self, value):
        slugs = [p["profession"].slug for p in value]
        if len(slugs) != len(set(slugs)):
            raise serializers.ValidationError("Un métier ne peut apparaître qu'une fois.")
        primaries = [p for p in value if p["profession"].kind == ProfessionKind.PRIMARY]
        if len(primaries) > Profession.MAX_PRIMARY:
            raise serializers.ValidationError(f"Au plus {Profession.MAX_PRIMARY} métiers principaux.")
        return value

    def validate(self, attrs):
        current = self.instance
        player_class = attrs.get("player_class", current.player_class if current else None)
        race = attrs.get("race", current.race if current else None)
        main_role = attrs.get("main_role", current.main_role if current else None)
        off_role = attrs.get("off_role", current.off_role if current else "")
        spec = attrs.get("specialization", current.specialization if current else None)
        errors = {}

        if race and player_class and not race.classes.filter(pk=player_class.pk).exists():
            errors["race"] = f"Un {race.name} ne peut pas être {player_class.name}."
        guild_faction = GuildSettings.load().faction
        if race and not race.available_for(guild_faction):
            errors["race"] = f"La guilde est {guild_faction.capitalize()}, cette race n'y est pas jouable."

        if player_class:
            allowed = player_class.roles
            if main_role and main_role not in allowed:
                errors["main_role"] = f"Un {player_class.name} ne peut pas être {Role(main_role).label}."
            if off_role and off_role not in allowed:
                errors["off_role"] = f"Un {player_class.name} ne peut pas être {Role(off_role).label}."
            if spec and spec.player_class_id != player_class.pk:
                errors["specialization"] = (
                    f"« {spec.name} » n'est pas une spécialisation de {player_class.name}."
                )
        if off_role and off_role == main_role:
            errors["off_role"] = "Le rôle secondaire doit différer du rôle principal."

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    # --- écriture ------------------------------------------------------------

    def _save_professions(self, character: Character, professions) -> None:
        character.professions.all().delete()
        CharacterProfession.objects.bulk_create(
            [CharacterProfession(character=character, **p) for p in professions]
        )

    @transaction.atomic
    def create(self, validated_data):
        professions = validated_data.pop("professions", [])
        is_main = validated_data.pop("is_main", False)
        character = Character.objects.create(**validated_data)
        self._save_professions(character, professions)
        if is_main:
            services.set_main(character)
        services.ensure_owner_has_main(character.owner)
        character.refresh_from_db()
        return character

    @transaction.atomic
    def update(self, instance, validated_data):
        professions = validated_data.pop("professions", None)
        is_main = validated_data.pop("is_main", None)
        validated_data.pop("owner", None)  # on ne transfère pas un perso
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if professions is not None:
            self._save_professions(instance, professions)
        if is_main:
            services.set_main(instance)
        # is_main=False est ignoré : on désigne un autre main plutôt que d'en avoir aucun.
        instance.refresh_from_db()
        return instance
