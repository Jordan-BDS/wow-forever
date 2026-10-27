from rest_framework.routers import DefaultRouter

from .views import CharacterViewSet

router = DefaultRouter()
router.register("characters", CharacterViewSet, basename="character")

urlpatterns = router.urls
