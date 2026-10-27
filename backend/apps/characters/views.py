from drf_spectacular.utils import extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from . import services
from .models import Character
from .serializers import CharacterSerializer


class IsOwnerOrOfficer(permissions.BasePermission):
    message = "Tu ne peux modifier que tes propres personnages."

    def has_object_permission(self, request, view, obj: Character) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.owner_id == request.user.pk or request.user.is_officer_or_above


class CharacterViewSet(viewsets.ModelViewSet):
    """Personnages de la guilde. Lecture pour tous ; écriture par le propriétaire ou un officier."""

    serializer_class = CharacterSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrOfficer]
    queryset = (
        Character.objects.select_related("owner", "player_class", "race", "specialization")
        .prefetch_related("professions__profession", "professions__specialization")
        .filter(owner__is_active=True)
    )

    def perform_create(self, serializer):
        owner = serializer.validated_data.get("owner", self.request.user)
        if owner != self.request.user and not self.request.user.is_officer_or_above:
            raise PermissionDenied("Seul un officier peut créer un personnage pour quelqu'un d'autre.")
        serializer.save(owner=owner)

    def perform_destroy(self, instance: Character):
        owner = instance.owner
        instance.delete()
        services.ensure_owner_has_main(owner)

    @extend_schema(request=None, responses=CharacterSerializer)
    @action(detail=True, methods=["post"], url_path="set-main")
    def set_main(self, request: Request, pk=None) -> Response:
        character = self.get_object()
        services.set_main(character)
        character.refresh_from_db()
        return Response(self.get_serializer(character).data)
