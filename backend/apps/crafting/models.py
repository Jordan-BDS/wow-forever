from django.conf import settings
from django.db import models

from apps.characters.models import Character
from apps.gamedata.models import Recipe


class CraftStatus(models.TextChoices):
    OPEN = "open", "Ouverte"
    TAKEN = "taken", "Prise en charge"
    DELIVERED = "delivered", "Livrée"
    CANCELLED = "cancelled", "Annulée"


class Materials(models.TextChoices):
    NONE = "none", "Aucun composant fourni"
    PARTIAL = "partial", "Composants partiels"
    ALL = "all", "Tous les composants fournis"


class CraftRequest(models.Model):
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="craft_requests"
    )
    recipe = models.ForeignKey(Recipe, on_delete=models.PROTECT, related_name="craft_requests")
    quantity = models.PositiveSmallIntegerField("Quantité", default=1)
    target_character = models.ForeignKey(
        Character,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="targeted_craft_requests",
        help_text="Crafteur ciblé, sinon ouvert à tous ceux qui connaissent la recette.",
    )
    materials = models.CharField(
        "Composants", max_length=8, choices=Materials.choices, default=Materials.NONE
    )
    note = models.CharField("Note", max_length=240, blank=True)
    status = models.CharField("Statut", max_length=10, choices=CraftStatus.choices, default=CraftStatus.OPEN)
    crafter = models.ForeignKey(
        Character, on_delete=models.SET_NULL, null=True, blank=True, related_name="craft_jobs"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    taken_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "demande de craft"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.recipe} pour {self.requester}"

    @property
    def is_active(self) -> bool:
        return self.status in (CraftStatus.OPEN, CraftStatus.TAKEN)
