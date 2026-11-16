from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .index_views import ImportRunSerializer
from .models import GAMEDATA_CACHE, GAMEDATA_TTL, ImportRun, Instance, PlayerClass, Profession, Race
from .serializers import GameDataSerializer


class GameDataView(APIView):
    """Toutes les données de référence en un appel (petit volume, mis en cache côté front)."""

    @extend_schema(responses=GameDataSerializer)
    def get(self, request: Request) -> Response:
        # Dix requêtes SQL pour des données qui ne changent qu'à un import : gardées `GAMEDATA_TTL` par
        # processus. Une retouche dans l'admin se voit donc au plus tard après ce délai.
        payload = cache.get(GAMEDATA_CACHE)
        if payload is not None:
            return Response(payload)
        data = {
            "classes": PlayerClass.objects.prefetch_related("specializations"),
            "races": Race.objects.prefetch_related("classes"),
            "professions": Profession.objects.prefetch_related("specializations"),
            "instances": Instance.objects.all(),
        }
        payload = GameDataSerializer(data).data
        last = ImportRun.objects.first()
        payload["import_run"] = ImportRunSerializer(last).data if last else None
        cache.set(GAMEDATA_CACHE, payload, GAMEDATA_TTL)
        return Response(payload)
