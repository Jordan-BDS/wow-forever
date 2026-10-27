from rest_framework.routers import DefaultRouter

from .views import MemberViewSet

router = DefaultRouter()
router.register("members", MemberViewSet, basename="member")

urlpatterns = router.urls
