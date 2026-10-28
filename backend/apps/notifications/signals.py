"""
À la suppression pure d'un événement ou d'un sondage (API, admin, cascade), on met en file le nettoyage
de ce que Discord en garde : événement planifié dans l'onglet « Événements » et message dans le salon.
L'annulation, elle, passe par les synchronisations habituelles (`event_sync` / `poll_sync`).
"""

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.events.models import Event
from apps.polls.models import Poll

from . import services


@receiver(pre_delete, sender=Event, dispatch_uid="notifications.event_deleted")
def _event_deleted(sender, instance: Event, **kwargs) -> None:
    services.event_deleted(instance)


@receiver(pre_delete, sender=Poll, dispatch_uid="notifications.poll_deleted")
def _poll_deleted(sender, instance: Poll, **kwargs) -> None:
    services.poll_deleted(instance)
