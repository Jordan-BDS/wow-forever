from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.notifications import services as notify

from . import services
from .models import Event, EventStatus, Signup
from .serializers import (
    DuplicateSerializer,
    EventSerializer,
    SignupManageSerializer,
    SignupSerializer,
    SignupWriteSerializer,
)

__all__ = ["EventViewSet", "SignupViewSet", "SignupWriteSerializer"]

EVENT_QUERYSET = Event.objects.select_related("organizer", "instance").prefetch_related(
    "signups__user", "signups__character__player_class"
)


class IsOrganizerOrOfficer(permissions.BasePermission):
    message = "Réservé à l'organisateur et aux officiers."

    def has_object_permission(self, request, view, obj: Event) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.can_manage(request.user)


class EventViewSet(viewsets.ModelViewSet):
    """Événements de l'agenda. Tout membre peut en créer ; l'organisateur ou un officier les gère."""

    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrganizerOrOfficer]
    queryset = EVENT_QUERYSET

    @extend_schema(
        parameters=[
            OpenApiParameter("from", str, description="Début de la fenêtre (ISO 8601)."),
            OpenApiParameter("to", str, description="Fin de la fenêtre (ISO 8601)."),
        ]
    )
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action != "list":
            return queryset
        start = parse_datetime(self.request.query_params.get("from", "") or "")
        end = parse_datetime(self.request.query_params.get("to", "") or "")
        if start:
            queryset = queryset.filter(starts_at__gte=start)
        if end:
            queryset = queryset.filter(starts_at__lt=end)
        if not start and not end:
            queryset = queryset.filter(starts_at__gte=timezone.now() - timedelta(days=1))
        return queryset

    def perform_create(self, serializer):
        organizer = serializer.validated_data.get("organizer", self.request.user)
        if organizer != self.request.user and not self.request.user.is_officer_or_above:
            raise PermissionDenied("Seul un officier peut désigner un autre organisateur.")
        event = serializer.save(organizer=organizer, created_by=self.request.user)
        notify.event_created(event)

    def perform_update(self, serializer):
        if "organizer" in serializer.validated_data and not self.request.user.is_officer_or_above:
            raise PermissionDenied("Seul un officier peut changer l'organisateur.")
        previous_start = serializer.instance.starts_at
        event = serializer.save()
        if event.starts_at != previous_start and event.effective_status == EventStatus.PLANNED:
            notify.event_rescheduled(event, previous_start)

    # --- actions sur l'événement ---------------------------------------------

    @extend_schema(request=None, responses=EventSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk=None) -> Response:
        event: Event = self.get_object()
        if event.status != EventStatus.CANCELLED:
            event.status = EventStatus.CANCELLED
            event.save(update_fields=["status", "updated_at"])
            notify.event_cancelled(event)
        return Response(self.get_serializer(event).data)

    @extend_schema(request=None, responses=EventSerializer)
    @action(detail=True, methods=["post"])
    def announce(self, request: Request, pk=None) -> Response:
        """Publie la composition actuelle dans le salon Discord de la guilde."""
        event: Event = self.get_object()
        notify.composition_announced(event)
        return Response(self.get_serializer(event).data)

    @extend_schema(request=None, responses=EventSerializer)
    @action(detail=True, methods=["post"])
    def restore(self, request: Request, pk=None) -> Response:
        event: Event = self.get_object()
        event.status = EventStatus.PLANNED
        event.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(event).data)

    @extend_schema(request=DuplicateSerializer, responses={201: EventSerializer})
    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def duplicate(self, request: Request, pk=None) -> Response:
        source: Event = self.get_object()
        serializer = DuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        starts_at = serializer.validated_data["starts_at"]
        shift = starts_at - source.starts_at
        copy = Event.objects.create(
            title=source.title,
            kind=source.kind,
            instance=source.instance,
            starts_at=starts_at,
            ends_at=source.ends_at + shift if source.ends_at else None,
            description=source.description,
            organizer=request.user,
            max_size=source.max_size,
            need_tanks=source.need_tanks,
            need_heals=source.need_heals,
            need_dps=source.need_dps,
            min_level=source.min_level,
            signup_deadline=source.signup_deadline + shift if source.signup_deadline else None,
            created_by=request.user,
        )
        copy = EVENT_QUERYSET.get(pk=copy.pk)
        return Response(self.get_serializer(copy).data, status=status.HTTP_201_CREATED)

    # --- inscriptions ---------------------------------------------------------

    @extend_schema(
        request=SignupWriteSerializer,
        responses={200: SignupSerializer, 201: SignupSerializer, 204: None},
        parameters=[
            OpenApiParameter("user", int, description="Officiers / organisateur : inscrire un autre joueur.")
        ],
    )
    @action(detail=True, methods=["post", "delete"], permission_classes=[permissions.IsAuthenticated])
    def signup(self, request: Request, pk=None) -> Response:
        """POST : s'inscrire ou modifier son inscription. DELETE : se désinscrire."""
        event: Event = self.get_object()
        target = self._target_user(request, event)
        acting_for_self = target.pk == request.user.pk

        if acting_for_self and not event.signups_open:
            raise ValidationError({"detail": "Les inscriptions sont closes pour cet événement."})

        if request.method == "DELETE":
            deleted, _ = Signup.objects.filter(event=event, user=target).delete()
            return Response(status=status.HTTP_204_NO_CONTENT if deleted else status.HTTP_404_NOT_FOUND)

        signup, created = services.upsert_signup(event, target, request.data)
        signup = Signup.objects.select_related("user", "character__player_class").get(pk=signup.pk)
        return Response(
            SignupSerializer(signup).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    def _target_user(self, request: Request, event: Event) -> User:
        raw = request.query_params.get("user")
        if not raw or str(request.user.pk) == raw:
            return request.user
        if not event.can_manage(request.user):
            raise PermissionDenied("Seul l'organisateur ou un officier peut inscrire quelqu'un d'autre.")
        try:
            return User.objects.get(pk=int(raw), is_active=True)
        except (User.DoesNotExist, ValueError) as exc:
            raise ValidationError({"user": "Joueur inconnu."}) from exc


class SignupViewSet(mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Gestion d'une inscription par l'organisateur ou un officier (placement, statut, retrait)."""

    serializer_class = SignupManageSerializer
    queryset = Signup.objects.select_related("event", "user", "character__player_class")

    def _check(self, signup: Signup) -> None:
        if not signup.event.can_manage(self.request.user):
            raise PermissionDenied("Réservé à l'organisateur et aux officiers.")

    def perform_update(self, serializer):
        self._check(serializer.instance)
        if serializer.instance.event.effective_status != EventStatus.PLANNED:
            raise PermissionDenied("L'événement n'est plus planifié.")
        previous_placement = serializer.instance.placement
        signup = serializer.save()
        if signup.placement != previous_placement:
            notify.placement_changed(signup)

    def perform_destroy(self, instance: Signup):
        self._check(instance)
        instance.delete()

    @extend_schema(responses=SignupSerializer)
    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        super().update(request, *args, **kwargs)
        signup = self.get_queryset().get(pk=kwargs["pk"])
        return Response(SignupSerializer(signup).data)

    @extend_schema(responses=SignupSerializer)
    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)
