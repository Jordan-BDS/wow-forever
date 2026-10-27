from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .index_views import ImportRunSerializer
from .models import ImportRun, Instance, PlayerClass, Profession, Race
from .serializers import GameDataSerializer


class GameDataView(APIView):
    """Toutes les données de référence en un appel (petit volume, mis en cache côté front)."""

    @extend_schema(responses=GameDataSerializer)
    def get(self, request: Request) -> Response:
        data = {
            "classes": PlayerClass.objects.prefetch_related("specializations"),
            "races": Race.objects.prefetch_related("classes"),
            "professions": Profession.objects.prefetch_related("specializations"),
            "instances": Instance.objects.all(),
        }
        payload = GameDataSerializer(data).data
        last = ImportRun.objects.first()
        payload["import_run"] = ImportRunSerializer(last).data if last else None
        return Response(payload)
