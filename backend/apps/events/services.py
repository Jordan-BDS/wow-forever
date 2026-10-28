from apps.accounts.models import User
from apps.notifications import services as notify

from .models import Event, Placement, Signup, SignupStatus
from .serializers import SignupWriteSerializer


def upsert_signup(event: Event, user: User, data: dict) -> tuple[Signup, bool]:
    """Crée ou met à jour une inscription. Lève ValidationError (DRF) si les données sont invalides."""
    serializer = SignupWriteSerializer(data=data, context={"event": event, "target_user": user})
    serializer.is_valid(raise_exception=True)
    signup, created = Signup.objects.update_or_create(
        event=event, user=user, defaults=serializer.validated_data
    )
    auto_place(signup)
    notify.event_sync(event)
    return signup, created


def has_room(event: Event, role: str) -> bool:
    """Reste-t-il une place confirmée pour ce rôle ? Sans besoin défini, c'est la taille max qui décide."""
    confirmed = [s for s in event.signups.all() if s.placement == Placement.CONFIRMED]
    need = event.needs_for(role)
    if need is not None and sum(1 for s in confirmed if s.role == role) >= need:
        return False
    return event.max_size is None or len(confirmed) < event.max_size


def auto_place(signup: Signup) -> None:
    """Confirme d'office un « Présent » tant qu'il reste de la place ; un « Absent » libère la sienne.

    Au-delà des places, l'inscrit reste « Non placé » et l'organisateur arbitre. Un placement déjà décidé
    (confirmé ou banc) n'est jamais remis en cause ici, sauf quand le joueur se déclare absent.
    """
    if signup.status == SignupStatus.ABSENT and signup.placement != Placement.UNPLACED:
        signup.placement = Placement.UNPLACED
        signup.save(update_fields=["placement", "updated_at"])
    elif (
        signup.status == SignupStatus.PRESENT
        and signup.placement == Placement.UNPLACED
        and has_room(signup.event, signup.role)
    ):
        signup.placement = Placement.CONFIRMED
        signup.save(update_fields=["placement", "updated_at"])


def remove_signup(event: Event, user: User) -> bool:
    """Retire l'inscription du joueur ; renvoie False s'il n'était pas inscrit."""
    deleted, _ = Signup.objects.filter(event=event, user=user).delete()
    if deleted:
        notify.event_sync(event)
    return bool(deleted)
