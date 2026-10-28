from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.characters.models import Character

from . import services
from .authentication import CompanionTokenAuthentication
from .format import ExportError
from .models import CharacterSnapshot, CompanionDevice, ImportBatch, ImportSource
from .serializers import (
    CharacterSnapshotSerializer,
    CompanionDeviceSerializer,
    CompanionStatusSerializer,
    ImportBatchSerializer,
    ImportRequestSerializer,
    PairingCodeSerializer,
    PairRequestSerializer,
    PairResponseSerializer,
    ReleaseSerializer,
    ResolveRequestSerializer,
)


class PairingThrottle(AnonRateThrottle):
    scope = "pairing"
    rate = "20/hour"


class PairingCodeView(APIView):
    """Génère un code d'appairage à saisir dans le compagnon (valable 10 minutes, un seul à la fois)."""

    @extend_schema(request=None, responses=PairingCodeSerializer)
    def post(self, request: Request) -> Response:
        pairing = services.create_pairing_code(request.user)
        return Response(PairingCodeSerializer(pairing).data, status=status.HTTP_201_CREATED)


class PairView(APIView):
    """Appelé par le compagnon : échange le code contre un jeton longue durée."""

    authentication_classes: list = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PairingThrottle]

    @extend_schema(request=PairRequestSerializer, responses=PairResponseSerializer)
    def post(self, request: Request) -> Response:
        serializer = PairRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            device, token = services.pair_device(
                serializer.validated_data["code"], serializer.validated_data["device_name"]
            )
        except ExportError as exc:
            raise ValidationError({"code": str(exc)}) from exc
        payload = {"token": token, "device": device, "display_name": device.user.display_name}
        return Response(PairResponseSerializer(payload).data, status=status.HTTP_201_CREATED)


class DeviceListView(APIView):
    """Mes compagnons appairés (y compris révoqués, pour l'historique)."""

    @extend_schema(responses=CompanionDeviceSerializer(many=True))
    def get(self, request: Request) -> Response:
        devices = CompanionDevice.objects.filter(user=request.user)
        return Response(CompanionDeviceSerializer(devices, many=True).data)


class DeviceRevokeView(APIView):
    @extend_schema(request=None, responses=CompanionDeviceSerializer)
    def post(self, request: Request, pk: int) -> Response:
        device = get_object_or_404(CompanionDevice, pk=pk, user=request.user)
        services.revoke_device(device)
        return Response(CompanionDeviceSerializer(device).data)


class ImportView(APIView):
    """Reçoit un code d'export : collé par le joueur (session) ou envoyé par le compagnon (jeton)."""

    authentication_classes = [CompanionTokenAuthentication, SessionAuthentication]

    @extend_schema(
        request=ImportRequestSerializer,
        responses={
            201: ImportBatchSerializer,
            400: OpenApiResponse(description="Code illisible"),
            409: OpenApiResponse(description="Déjà importé"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = request.auth if isinstance(request.auth, CompanionDevice) else None
        source = ImportSource.COMPANION if device else ImportSource.PASTE
        try:
            batch = services.import_code(
                request.user, serializer.validated_data["code"], source=source, device=device
            )
        except services.DuplicateImport as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ExportError as exc:
            raise ValidationError({"code": str(exc)}) from exc
        return Response(ImportBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class ImportHistoryView(APIView):
    @extend_schema(responses=ImportBatchSerializer(many=True))
    def get(self, request: Request) -> Response:
        batches = (
            ImportBatch.objects.filter(user=request.user)
            .select_related("device")
            .prefetch_related("snapshots__character", "snapshots__candidate")[:20]
        )
        return Response(ImportBatchSerializer(batches, many=True).data)


class PendingSnapshotsView(APIView):
    """Personnages du jeu encore à rattacher, ou ignorés faute de niveau."""

    @extend_schema(responses=CharacterSnapshotSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(CharacterSnapshotSerializer(services.pending_snapshots(request.user), many=True).data)


class ResolveSnapshotView(APIView):
    @extend_schema(request=ResolveRequestSerializer, responses=CharacterSnapshotSerializer)
    def post(self, request: Request, pk: int) -> Response:
        snapshot = get_object_or_404(
            CharacterSnapshot.objects.select_related("candidate", "batch"), pk=pk, user=request.user
        )
        serializer = ResolveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        character = None
        if serializer.validated_data.get("character_id"):
            character = get_object_or_404(
                Character, pk=serializer.validated_data["character_id"], owner=request.user
            )
        try:
            result = services.resolve_snapshot(snapshot, serializer.validated_data["action"], character)
        except ExportError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(CharacterSnapshotSerializer(result).data)


class ReleaseView(APIView):
    """Dernière release du compagnon (null tant qu'aucune n'est publiée)."""

    @extend_schema(responses={200: ReleaseSerializer, 204: OpenApiResponse(description="Aucune release")})
    def get(self, request: Request) -> Response:
        release = services.latest_release()
        if release is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(ReleaseSerializer(release).data)


class CompanionStatusView(APIView):
    """Pour le compagnon : qui je suis, et mon dernier import."""

    authentication_classes = [CompanionTokenAuthentication]

    @extend_schema(responses=CompanionStatusSerializer)
    def get(self, request: Request) -> Response:
        device = request.auth
        last = (
            ImportBatch.objects.filter(user=request.user)
            .prefetch_related("snapshots__character", "snapshots__candidate")
            .first()
        )
        payload = {"display_name": request.user.display_name, "device": device, "last_import": last}
        return Response(CompanionStatusSerializer(payload).data)
