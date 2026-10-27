from rest_framework.routers import DefaultRouter

from .views import EventViewSet, SignupViewSet

router = DefaultRouter()
router.register("events", EventViewSet, basename="event")
router.register("signups", SignupViewSet, basename="signup")

urlpatterns = router.urls
