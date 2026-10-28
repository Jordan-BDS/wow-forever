from rest_framework import serializers

from .models import CharacterSnapshot, CompanionDevice, ImportBatch, SnapshotStatus


class PairingCodeSerializer(serializers.Serializer):
    code = serializers.CharField()
    expires_at = serializers.DateTimeField()


class PairRequestSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=8)
    device_name = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class CompanionDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanionDevice
        fields = ["id", "name", "token_prefix", "created_at", "last_seen_at", "revoked_at"]
        read_only_fields = fields


class PairResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    device = CompanionDeviceSerializer()
    display_name = serializers.CharField()


class ImportRequestSerializer(serializers.Serializer):
    code = serializers.CharField(trim_whitespace=True)


class LinkedCharacterSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    full_name = serializers.CharField()
    level = serializers.IntegerField()


class CharacterSnapshotSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    level = serializers.SerializerMethodField()
    character = LinkedCharacterSerializer(read_only=True, allow_null=True)
    candidate = LinkedCharacterSerializer(read_only=True, allow_null=True)
    low_level = serializers.SerializerMethodField()

    class Meta:
        model = CharacterSnapshot
        fields = [
            "id", "guid", "name", "surname", "full_name", "realm", "level", "exported_at", "status", "note",
            "low_level", "character", "candidate",
        ]  # fmt: skip
        read_only_fields = fields

    def get_level(self, snapshot: CharacterSnapshot) -> int | None:
        level = snapshot.data.get("level") if isinstance(snapshot.data, dict) else None
        return level if isinstance(level, int) else None

    def get_low_level(self, snapshot: CharacterSnapshot) -> bool:
        return snapshot.status == SnapshotStatus.IGNORED and snapshot.note == "low_level"


class ImportBatchSerializer(serializers.ModelSerializer):
    snapshots = CharacterSnapshotSerializer(many=True, read_only=True)
    device = CompanionDeviceSerializer(read_only=True, allow_null=True)

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "source",
            "device",
            "received_at",
            "format_version",
            "addon_version",
            "summary",
            "snapshots",
        ]
        read_only_fields = fields


class ResolveRequestSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["merge", "create", "ignore"])
    character_id = serializers.IntegerField(required=False, allow_null=True)


class ReleaseAssetsSerializer(serializers.Serializer):
    windows = serializers.URLField(required=False)
    macos = serializers.URLField(required=False)
    addon = serializers.URLField(required=False)


class ReleaseSerializer(serializers.Serializer):
    version = serializers.CharField()
    tag = serializers.CharField()
    published_at = serializers.DateTimeField(allow_null=True)
    url = serializers.URLField()
    assets = ReleaseAssetsSerializer()


class CompanionStatusSerializer(serializers.Serializer):
    display_name = serializers.CharField()
    device = CompanionDeviceSerializer()
    last_import = ImportBatchSerializer(allow_null=True)
