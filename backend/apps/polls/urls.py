from rest_framework.routers import DefaultRouter

from .views import PollViewSet, ProposalViewSet

router = DefaultRouter()
router.register("polls", PollViewSet, basename="poll")
router.register("proposals", ProposalViewSet, basename="proposal")

urlpatterns = router.urls
