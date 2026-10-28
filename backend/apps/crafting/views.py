from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.characters.models import Character
from apps.notifications import services as notify

from .models import CraftRequest, CraftStatus
from .serializers import CraftRequestSerializer, TakeSerializer

QUERYSET = CraftRequest.objects.select_related(
    "requester",
    "recipe__profession",
    "recipe__product__item_set",
    "target_character__player_class",
    "target_character__owner",
    "crafter__player_class",
    "crafter__owner",
)


def my_recipe_ids(user) -> set[int]:
    return set(
        Character.objects.filter(owner=user)
        .values_list("known_recipes__recipe_id", flat=True)
        .exclude(known_recipes__recipe_id=None)
    )


class CraftRequestViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """Demandes de craft : création par tout membre ; prise, livraison et annulation selon le rôle."""

    serializer_class = CraftRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("scope", str, description="open (défaut), mine, doable, all"),
        ]
    )
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = QUERYSET
        if self.action != "list":
            return queryset
        scope = self.request.query_params.get("scope", "open")
        user = self.request.user
        if scope == "mine":
            return queryset.filter(requester=user)
        if scope == "doable":
            known = my_recipe_ids(user)
            mine_chars = Character.objects.filter(owner=user)
            return queryset.filter(
                Q(status=CraftStatus.OPEN, recipe_id__in=known)
                | Q(status=CraftStatus.TAKEN, crafter__in=mine_chars)
            ).exclude(requester=user)
        if scope == "all":
            return queryset
        return queryset.filter(status=CraftStatus.OPEN)

    def perform_create(self, serializer):
        request = serializer.save(requester=self.request.user)
        notify.craft_requested(request)

    def _can_manage(self, craft: CraftRequest) -> bool:
        user = self.request.user
        return user.pk == craft.requester_id or user.is_officer_or_above

    @extend_schema(request=TakeSerializer, responses=CraftRequestSerializer)
    @action(detail=True, methods=["post"])
    def take(self, request: Request, pk=None) -> Response:
        craft: CraftRequest = self.get_object()
        if craft.status != CraftStatus.OPEN:
            raise ValidationError({"detail": "Cette demande n'est plus ouverte."})
        serializer = TakeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        character: Character = serializer.validated_data["character"]
        if character.owner_id != request.user.pk and not request.user.is_officer_or_above:
            raise PermissionDenied("Ce personnage n'est pas à toi.")
        if not character.known_recipes.filter(recipe=craft.recipe).exists():
            raise ValidationError({"character": f"{character.name} ne connaît pas cette recette."})
        if (
            craft.target_character_id
            and craft.target_character_id != character.pk
            and not request.user.is_officer_or_above
        ):
            raise PermissionDenied("Cette demande cible un autre crafteur.")
        craft.status = CraftStatus.TAKEN
        craft.crafter = character
        craft.taken_at = timezone.now()
        craft.save()
        notify.craft_updated(craft)
        return Response(self.get_serializer(craft).data)

    @extend_schema(request=None, responses=CraftRequestSerializer)
    @action(detail=True, methods=["post"])
    def deliver(self, request: Request, pk=None) -> Response:
        craft: CraftRequest = self.get_object()
        if craft.status != CraftStatus.TAKEN:
            raise ValidationError({"detail": "La demande doit être prise en charge avant d'être livrée."})
        is_crafter = craft.crafter and craft.crafter.owner_id == request.user.pk
        if not is_crafter and not self._can_manage(craft):
            raise PermissionDenied("Seul le crafteur, le demandeur ou un officier peut marquer la livraison.")
        craft.status = CraftStatus.DELIVERED
        craft.delivered_at = timezone.now()
        craft.save()
        notify.craft_updated(craft)
        return Response(self.get_serializer(craft).data)

    @extend_schema(request=None, responses=CraftRequestSerializer)
    @action(detail=True, methods=["post"])
    def release(self, request: Request, pk=None) -> Response:
        """Le crafteur rend une demande prise en charge : elle redevient ouverte."""
        craft: CraftRequest = self.get_object()
        if craft.status != CraftStatus.TAKEN:
            raise ValidationError({"detail": "Cette demande n'est pas prise en charge."})
        is_crafter = craft.crafter and craft.crafter.owner_id == request.user.pk
        if not is_crafter and not request.user.is_officer_or_above:
            raise PermissionDenied("Seul le crafteur ou un officier peut rendre la demande.")
        previous_crafter = craft.crafter
        craft.status = CraftStatus.OPEN
        craft.crafter = None
        craft.taken_at = None
        craft.save()
        if previous_crafter:
            notify.craft_released(craft, previous_crafter)
        return Response(self.get_serializer(craft).data)

    @extend_schema(request=None, responses=CraftRequestSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk=None) -> Response:
        craft: CraftRequest = self.get_object()
        if not craft.is_active:
            raise ValidationError({"detail": "Cette demande est déjà close."})
        if not self._can_manage(craft):
            raise PermissionDenied("Seul le demandeur ou un officier peut annuler.")
        craft.status = CraftStatus.CANCELLED
        craft.save()
        notify.craft_updated(craft)
        return Response(self.get_serializer(craft).data)
