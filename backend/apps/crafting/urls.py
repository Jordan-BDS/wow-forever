from rest_framework.routers import DefaultRouter

from .views import CraftRequestViewSet

router = DefaultRouter()
router.register("craft-requests", CraftRequestViewSet, basename="craft-request")

urlpatterns = router.urls
