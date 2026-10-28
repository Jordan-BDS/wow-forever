from apps.accounts.models import User
from apps.notifications import services as notify

from .models import Event, Signup
from .serializers import SignupWriteSerializer


def upsert_signup(event: Event, user: User, data: dict) -> tuple[Signup, bool]:
    """Crée ou met à jour une inscription. Lève ValidationError (DRF) si les données sont invalides."""
    serializer = SignupWriteSerializer(data=data, context={"event": event, "target_user": user})
    serializer.is_valid(raise_exception=True)
    result = Signup.objects.update_or_create(event=event, user=user, defaults=serializer.validated_data)
    notify.event_sync(event)
    return result


def remove_signup(event: Event, user: User) -> bool:
    """Retire l'inscription du joueur ; renvoie False s'il n'était pas inscrit."""
    deleted, _ = Signup.objects.filter(event=event, user=user).delete()
    if deleted:
        notify.event_sync(event)
    return bool(deleted)
