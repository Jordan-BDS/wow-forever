from django.urls import path

from . import views

urlpatterns = [
    path("pairing-code/", views.PairingCodeView.as_view(), name="sync-pairing-code"),
    path("pair/", views.PairView.as_view(), name="sync-pair"),
    path("devices/", views.DeviceListView.as_view(), name="sync-devices"),
    path("devices/<int:pk>/revoke/", views.DeviceRevokeView.as_view(), name="sync-device-revoke"),
    path("import/", views.ImportView.as_view(), name="sync-import"),
    path("imports/", views.ImportHistoryView.as_view(), name="sync-imports"),
    path("pending/", views.PendingSnapshotsView.as_view(), name="sync-pending"),
    path("pending/<int:pk>/resolve/", views.ResolveSnapshotView.as_view(), name="sync-resolve"),
    path("release/", views.ReleaseView.as_view(), name="sync-release"),
    path("companion/me/", views.CompanionStatusView.as_view(), name="sync-companion-me"),
    path(
        "characters/<int:pk>/progress/", views.CharacterProgressView.as_view(), name="sync-character-progress"
    ),
    path("rankings/", views.RankingsView.as_view(), name="sync-rankings"),
]
