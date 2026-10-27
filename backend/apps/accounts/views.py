from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Availability, DeactivationReason, User
from .permissions import IsGM, IsOfficerOrAbove
from .serializers import (
    AvailabilitySlotSerializer,
    GuildAvailabilitySerializer,
    MemberSerializer,
    MeUpdateSerializer,
    SetRoleSerializer,
)


class MyAvailabilityView(APIView):
    """Mes créneaux de disponibilité. Le PUT remplace la liste entière."""

    @extend_schema(responses=AvailabilitySlotSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(AvailabilitySlotSerializer(request.user.availabilities.all(), many=True).data)

    @extend_schema(
        request=AvailabilitySlotSerializer(many=True), responses=AvailabilitySlotSerializer(many=True)
    )
    def put(self, request: Request) -> Response:
        serializer = AvailabilitySlotSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            request.user.availabilities.all().delete()
            Availability.objects.bulk_create(
                [Availability(user=request.user, **slot) for slot in serializer.validated_data]
            )
        return Response(AvailabilitySlotSerializer(request.user.availabilities.all(), many=True).data)


class GuildAvailabilityView(APIView):
    """Créneaux de tous les membres actifs, pour la vue agrégée."""

    @extend_schema(responses=GuildAvailabilitySerializer(many=True))
    def get(self, request: Request) -> Response:
        slots = Availability.objects.filter(user__is_active=True).select_related("user")
        return Response(GuildAvailabilitySerializer(slots, many=True).data)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(APIView):
    """Profil de l'utilisateur connecté. Le GET pose aussi le cookie CSRF."""

    @extend_schema(responses=MemberSerializer)
    def get(self, request: Request) -> Response:
        return Response(MemberSerializer(request.user).data)

    @extend_schema(request=MeUpdateSerializer, responses=MemberSerializer)
    def patch(self, request: Request) -> Response:
        serializer = MeUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MemberSerializer(request.user).data)


class MemberViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Les membres de la guilde (lecture pour tous, actions réservées aux officiers / GM)."""

    queryset = User.objects.all()
    serializer_class = MemberSerializer

    def _ensure_can_manage(self, target: User) -> None:
        actor: User = self.request.user
        if target.pk == actor.pk:
            raise PermissionDenied("Tu ne peux pas agir sur ton propre compte.")
        if not actor.outranks(target):
            raise PermissionDenied("Tu ne peux agir que sur un membre de rang inférieur au tien.")

    @extend_schema(request=SetRoleSerializer, responses=MemberSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsGM])
    def role(self, request: Request, pk=None) -> Response:
        target = self.get_object()
        if target.pk == request.user.pk:
            raise PermissionDenied("Tu ne peux pas changer ton propre rôle.")
        serializer = SetRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target.site_role = serializer.validated_data["site_role"]
        target.save(update_fields=["site_role"])
        return Response(MemberSerializer(target).data)

    @extend_schema(request=None, responses=MemberSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsOfficerOrAbove])
    def deactivate(self, request: Request, pk=None) -> Response:
        target = self.get_object()
        self._ensure_can_manage(target)
        if target.is_active:
            services.deactivate_user(target, DeactivationReason.MANUAL)
        return Response(MemberSerializer(target).data)

    @extend_schema(request=None, responses=MemberSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsOfficerOrAbove])
    def reactivate(self, request: Request, pk=None) -> Response:
        target = self.get_object()
        self._ensure_can_manage(target)
        if not target.is_active:
            services.reactivate_user(target)
        return Response(MemberSerializer(target).data, status=status.HTTP_200_OK)
