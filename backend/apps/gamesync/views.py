from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsGM
from apps.characters.models import Character

from . import auctions, services
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


class CompanionStateView(APIView):
    """Pour le compagnon : l'état fusionné de mes personnages (compteurs, journal, créatures, événements), à
    recopier dans l'addon d'un PC au lancement, jeu fermé, pour qu'aucune installation ne reparte de zéro."""

    authentication_classes = [CompanionTokenAuthentication]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        from . import progress

        return Response(progress.companion_state(request.user))


# --- fiche vivante et classements -------------------------------------------------------------------


class CharacterProgressView(APIView):
    """État d'un personnage tel que reçu du jeu (dernier instantané) : compteurs, accès, verrous…"""

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request, pk: int) -> Response:
        character = get_object_or_404(Character.objects.select_related("owner"), pk=pk)
        from . import progress

        data = progress.character_progress(character)
        return Response({"available": data is not None, **(data or {})})


class WantedView(APIView):
    """La page Wanted : têtes mises à prix détaillées (morts, kills), chasseurs et victimes, par période."""

    @extend_schema(
        parameters=[
            OpenApiParameter("period", OpenApiTypes.STR, description="week (défaut), month, season, all")
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        from django.core.cache import cache

        from . import rankings, wanted

        period = request.query_params.get("period", "week")
        period = period if period in rankings.PERIODS else "week"
        key = f"gamesync:wanted:{period}"
        data = cache.get(key)
        if data is None:
            start, end = rankings.period_bounds(period, timezone.now())
            data = {"period": period, **wanted.wanted_report(None, start, end)}
            cache.set(key, data, 60)
        return Response(data)


class AddonErrorsView(APIView):
    """GM : erreurs des collecteurs remontées par les addons de la guilde (14 derniers jours)."""

    permission_classes = [IsGM]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        return Response({"errors": services.addon_errors()})


# --- hôtel des ventes ---------------------------------------------------------------------------------


def _page(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


class CanUseAuctions(permissions.BasePermission):
    """Envoyer et lire les prix : la règle est dans `auctions.can_upload`, nulle part ailleurs."""

    message = "Réservé au GM."

    def has_permission(self, request, view) -> bool:
        return auctions.can_upload(request.user)


class AuctionRightsView(APIView):
    """Pour le compagnon : ce compte peut-il envoyer les scans de l'hôtel des ventes ? Il ne lit le fichier de
    scan et n'envoie quoi que ce soit que si oui."""

    authentication_classes = [CompanionTokenAuthentication, SessionAuthentication]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        return Response({"upload": auctions.can_upload(request.user)})


class AuctionScansView(APIView):
    """GM : le compagnon envoie un scan complet de l'hôtel des ventes (POST), le site liste le dernier scan
    comparé à un scan de référence (GET)."""

    authentication_classes = [CompanionTokenAuthentication, SessionAuthentication]
    permission_classes = [CanUseAuctions]

    @extend_schema(
        parameters=[
            OpenApiParameter("house", OpenApiTypes.STR, description="hôtel (défaut : le dernier scanné)"),
            OpenApiParameter("q", OpenApiTypes.STR, description="nom ou ID d'objet"),
            OpenApiParameter(
                "sort", OpenApiTypes.STR, description="name (défaut), price, listed, up, down, sold, posted"
            ),
            OpenApiParameter("since", OpenApiTypes.STR, description="prev (défaut), day, week"),
            OpenApiParameter("page", OpenApiTypes.INT),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        params = request.query_params
        return Response(
            auctions.overview(
                house=params.get("house", ""),
                q=params.get("q", ""),
                sort=params.get("sort", "name"),
                since=params.get("since", "prev"),
                page=_page(params.get("page")),
            )
        )

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={
            201: OpenApiTypes.OBJECT,
            400: OpenApiResponse(description="Scan illisible"),
            409: OpenApiResponse(description="Déjà reçu"),
        },
    )
    def post(self, request: Request) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        device = request.auth if isinstance(request.auth, CompanionDevice) else None
        try:
            scan = auctions.store_scan(
                request.user, data.get("house"), data.get("scanned_at"), data.get("items"), device=device
            )
        except auctions.DuplicateScan as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except auctions.AuctionError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(auctions.scan_summary(scan), status=status.HTTP_201_CREATED)


class AuctionItemView(APIView):
    """GM : l'historique de prix d'un objet dans un hôtel des ventes."""

    permission_classes = [CanUseAuctions]

    @extend_schema(
        parameters=[OpenApiParameter("house", OpenApiTypes.STR)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request, item_id: int) -> Response:
        return Response(auctions.item_history(item_id, request.query_params.get("house", "")))


class AuctionRecipesView(APIView):
    """GM : ses recettes favorites, ou celles que trouve `q`, avec le coût des composants et le prix du
    produit au dernier scan."""

    permission_classes = [CanUseAuctions]

    @extend_schema(
        parameters=[
            OpenApiParameter("house", OpenApiTypes.STR, description="hôtel (défaut : le dernier scanné)"),
            OpenApiParameter("q", OpenApiTypes.STR, description="recherche (défaut : les favorites)"),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        params = request.query_params
        return Response(
            auctions.recipe_costs(request.user, house=params.get("house", ""), q=params.get("q", ""))
        )


class AuctionFavoriteRecipeView(APIView):
    """GM : suivre (PUT) ou ne plus suivre (DELETE) une recette."""

    permission_classes = [CanUseAuctions]

    @extend_schema(request=None, responses={204: None, 404: OpenApiResponse(description="Recette inconnue")})
    def put(self, request: Request, recipe_id: int) -> Response:
        try:
            auctions.set_favorite(request.user, recipe_id, True)
        except auctions.AuctionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request, recipe_id: int) -> Response:
        auctions.set_favorite(request.user, recipe_id, False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RankingsView(APIView):
    """Classements de guilde pour une période (week, month, season, all), par joueur ou par personnage."""

    @extend_schema(
        parameters=[
            OpenApiParameter("period", OpenApiTypes.STR, description="week (défaut), month, season, all"),
            OpenApiParameter("by", OpenApiTypes.STR, description="player (défaut) ou character"),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        from django.core.cache import cache

        from . import rankings

        period = request.query_params.get("period", "week")
        by = request.query_params.get("by", "player")
        key = f"gamesync:rankings:{period}:{by}"
        data = cache.get(key)
        if data is None:
            data = rankings.compute_rankings(period, by)
            cache.set(key, data, 60)
        return Response(data)
