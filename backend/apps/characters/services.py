from django.db import transaction

from .models import Character


@transaction.atomic
def set_main(character: Character) -> None:
    Character.objects.filter(owner=character.owner, is_main=True).exclude(pk=character.pk).update(
        is_main=False
    )
    if not character.is_main:
        character.is_main = True
        character.save(update_fields=["is_main"])


@transaction.atomic
def ensure_owner_has_main(owner) -> None:
    """S'il reste des persos et aucun main (après création ou suppression), le plus haut devient main."""
    characters = Character.objects.filter(owner=owner)
    if characters.exists() and not characters.filter(is_main=True).exists():
        first = characters.order_by("-level", "created_at").first()
        first.is_main = True
        first.save(update_fields=["is_main"])
