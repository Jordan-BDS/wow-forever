from rest_framework import serializers

from .models import PlayerClass, Profession, ProfessionSpecialization, Race, Specialization


class SpecializationSerializer(serializers.ModelSerializer):
    roles = serializers.ListField(child=serializers.CharField())

    class Meta:
        model = Specialization
        fields = ["id", "slug", "name", "roles"]


class PlayerClassSerializer(serializers.ModelSerializer):
    specializations = SpecializationSerializer(many=True)
    roles = serializers.ListField(child=serializers.CharField())

    class Meta:
        model = PlayerClass
        fields = ["id", "slug", "name", "color", "roles", "specializations"]


class RaceSerializer(serializers.ModelSerializer):
    classes = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)

    class Meta:
        model = Race
        fields = ["id", "slug", "name", "faction", "classes"]


class ProfessionSpecializationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfessionSpecialization
        fields = ["id", "slug", "name"]


class ProfessionSerializer(serializers.ModelSerializer):
    specializations = ProfessionSpecializationSerializer(many=True)

    class Meta:
        model = Profession
        fields = ["id", "slug", "name", "kind", "specializations"]


class GameDataSerializer(serializers.Serializer):
    classes = PlayerClassSerializer(many=True)
    races = RaceSerializer(many=True)
    professions = ProfessionSerializer(many=True)
