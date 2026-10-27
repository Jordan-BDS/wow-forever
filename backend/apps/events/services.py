from apps.accounts.models import User

from .models import Event, Signup
from .serializers import SignupWriteSerializer


def upsert_signup(event: Event, user: User, data: dict) -> tuple[Signup, bool]:
    """Crée ou met à jour une inscription. Lève ValidationError (DRF) si les données sont invalides."""
    serializer = SignupWriteSerializer(data=data, context={"event": event, "target_user": user})
    serializer.is_valid(raise_exception=True)
    return Signup.objects.update_or_create(event=event, user=user, defaults=serializer.validated_data)
