from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import User
from apps.characters.models import Character
from apps.characters.serializers import OwnerSerializer
from apps.gamedata.models import Instance, Role

from .models import (
    INSTANCE_KIND_FOR_EVENT,
    Event,
    EventKind,
    EventStatus,
    Placement,
    Signup,
    SignupStatus,
)


class SignupCharacterSerializer(serializers.ModelSerializer):
    player_class = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = Character
        fields = ["id", "name", "player_class", "level", "main_role", "off_role"]
        read_only_fields = fields


class SignupSerializer(serializers.ModelSerializer):
    user = OwnerSerializer(read_only=True)
    character = SignupCharacterSerializer(read_only=True)

    class Meta:
        model = Signup
        fields = ["id", "event", "user", "character", "role", "status", "comment", "placement", "updated_at"]
        read_only_fields = fields


class SignupWriteSerializer(serializers.Serializer):
    """Inscription (création ou mise à jour) : personnage, rôle, statut, commentaire."""

    character = serializers.PrimaryKeyRelatedField(queryset=Character.objects.all())
    role = serializers.ChoiceField(choices=Role.choices)
    status = serializers.ChoiceField(choices=SignupStatus.choices, default=SignupStatus.PRESENT)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=240, default="")

    def validate(self, attrs):
        event: Event = self.context["event"]
        target: User = self.context["target_user"]
        character: Character = attrs["character"]
        if character.owner_id != target.pk:
            raise serializers.ValidationError(
                {"character": "Ce personnage n'appartient pas au joueur inscrit."}
            )
        if attrs["role"] not in (character.main_role, character.off_role):
            raise serializers.ValidationError({"role": f"{character.name} ne joue pas ce rôle."})
        if event.min_level and character.level < event.min_level:
            raise serializers.ValidationError(
                {"character": f"Niveau {event.min_level} requis, {character.name} est {character.level}."}
            )
        return attrs


class SignupManageSerializer(serializers.ModelSerializer):
    """Modification par l'organisateur : placement, et au besoin statut / rôle / commentaire."""

    class Meta:
        model = Signup
        fields = ["role", "status", "comment", "placement"]

    def validate_role(self, value):
        character = self.instance.character
        if value not in (character.main_role, character.off_role):
            raise serializers.ValidationError(f"{character.name} ne joue pas ce rôle.")
        return value


class RoleCountSerializer(serializers.Serializer):
    tank = serializers.IntegerField()
    heal = serializers.IntegerField()
    dps = serializers.IntegerField()


class EventSerializer(serializers.ModelSerializer):
    organizer = OwnerSerializer(read_only=True)
    organizer_id = serializers.PrimaryKeyRelatedField(
        source="organizer",
        queryset=User.objects.filter(is_active=True),
        write_only=True,
        required=False,
        help_text="Officiers seulement : désigner un autre organisateur.",
    )
    instance = serializers.SlugRelatedField(
        slug_field="slug", queryset=Instance.objects.all(), allow_null=True, required=False
    )
    effective_status = serializers.ChoiceField(choices=EventStatus.choices, read_only=True)
    signups_open = serializers.BooleanField(read_only=True)
    signups = SignupSerializer(many=True, read_only=True)
    confirmed = serializers.SerializerMethodField()
    candidates = serializers.SerializerMethodField()
    my_signup = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "kind",
            "instance",
            "starts_at",
            "ends_at",
            "description",
            "organizer",
            "organizer_id",
            "max_size",
            "need_tanks",
            "need_heals",
            "need_dps",
            "min_level",
            "signup_deadline",
            "status",
            "effective_status",
            "signups_open",
            "signups",
            "confirmed",
            "candidates",
            "my_signup",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "created_at", "updated_at"]
        extra_kwargs = {"min_level": {"min_value": 1, "max_value": 60}, "max_size": {"min_value": 1}}

    def validate(self, attrs):
        current = self.instance
        get = lambda name: attrs.get(name, getattr(current, name) if current else None)  # noqa: E731
        kind, instance = get("kind"), get("instance")
        starts_at, ends_at, deadline = get("starts_at"), get("ends_at"), get("signup_deadline")
        errors = {}
        if instance and kind:
            expected = INSTANCE_KIND_FOR_EVENT[EventKind(kind)]
            if expected is None or instance.kind != expected:
                errors["instance"] = (
                    f"« {instance.name} » ne correspond pas à un événement de type {EventKind(kind).label}."
                )
        if starts_at and ends_at and ends_at <= starts_at:
            errors["ends_at"] = "La fin doit être après le début."
        if starts_at and deadline and deadline > starts_at:
            errors["signup_deadline"] = "La clôture des inscriptions doit précéder le début."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def _counts(self, event: Event, predicate) -> dict:
        counts = {Role.TANK.value: 0, Role.HEAL.value: 0, Role.DPS.value: 0}
        for signup in event.signups.all():
            if predicate(signup):
                counts[signup.role] += 1
        return counts

    @extend_schema_field(RoleCountSerializer)
    def get_confirmed(self, event: Event) -> dict:
        return self._counts(event, lambda s: s.placement == Placement.CONFIRMED)

    @extend_schema_field(RoleCountSerializer)
    def get_candidates(self, event: Event) -> dict:
        return self._counts(event, lambda s: s.status != SignupStatus.ABSENT)

    @extend_schema_field(SignupSerializer(allow_null=True))
    def get_my_signup(self, event: Event) -> dict | None:
        user = self.context["request"].user
        mine = next((s for s in event.signups.all() if s.user_id == user.pk), None)
        return SignupSerializer(mine).data if mine else None


class DuplicateSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
