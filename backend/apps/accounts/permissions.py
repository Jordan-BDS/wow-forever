from rest_framework.permissions import BasePermission


class IsOfficerOrAbove(BasePermission):
    message = "Réservé aux officiers et au GM."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_officer_or_above)


class IsGM(BasePermission):
    message = "Réservé au GM."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_gm)
