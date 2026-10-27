from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.characters.models import Character
from apps.gamedata.models import Instance, InstanceKind, Role


class EventKind(models.TextChoices):
    RAID = "raid", "Raid"
    DUNGEON = "dungeon", "Donjon"
    PVP = "pvp", "PvP"
    SOCIAL = "social", "Social / autre"


# Type d'instance attendu pour chaque type d'événement (None = pas d'instance).
INSTANCE_KIND_FOR_EVENT = {
    EventKind.RAID: InstanceKind.RAID,
    EventKind.DUNGEON: InstanceKind.DUNGEON,
    EventKind.PVP: InstanceKind.BATTLEGROUND,
    EventKind.SOCIAL: None,
}


class EventStatus(models.TextChoices):
    PLANNED = "planned", "Planifié"
    CANCELLED = "cancelled", "Annulé"
    DONE = "done", "Terminé"


class SignupStatus(models.TextChoices):
    PRESENT = "present", "Présent"
    MAYBE = "maybe", "Peut-être"
    LATE = "late", "En retard"
    ABSENT = "absent", "Absent"


class Placement(models.TextChoices):
    UNPLACED = "unplaced", "Non placé"
    CONFIRMED = "confirmed", "Confirmé"
    BENCH = "bench", "Banc"


DEFAULT_DURATION = timedelta(hours=3)


class Event(models.Model):
    title = models.CharField("Titre", max_length=120)
    kind = models.CharField("Type", max_length=16, choices=EventKind.choices)
    instance = models.ForeignKey(
        Instance, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Instance"
    )
    starts_at = models.DateTimeField("Début")
    ends_at = models.DateTimeField("Fin", null=True, blank=True)
    description = models.TextField("Description", blank=True)
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="organized_events"
    )
    max_size = models.PositiveSmallIntegerField("Taille max", null=True, blank=True)
    need_tanks = models.PositiveSmallIntegerField("Tanks souhaités", null=True, blank=True)
    need_heals = models.PositiveSmallIntegerField("Heals souhaités", null=True, blank=True)
    need_dps = models.PositiveSmallIntegerField("DPS souhaités", null=True, blank=True)
    min_level = models.PositiveSmallIntegerField("Niveau minimum", null=True, blank=True)
    signup_deadline = models.DateTimeField("Clôture des inscriptions", null=True, blank=True)
    status = models.CharField(
        "Statut", max_length=16, choices=EventStatus.choices, default=EventStatus.PLANNED
    )
    reminder_sent_at = models.DateTimeField("Rappel envoyé le", null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "événement"
        ordering = ["starts_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.starts_at:%d/%m %H:%M})"

    @property
    def effective_ends_at(self):
        return self.ends_at or self.starts_at + DEFAULT_DURATION

    @property
    def effective_status(self) -> str:
        if self.status != EventStatus.PLANNED:
            return self.status
        if timezone.now() >= self.effective_ends_at:
            return EventStatus.DONE
        return EventStatus.PLANNED

    @property
    def signups_open(self) -> bool:
        if self.effective_status != EventStatus.PLANNED:
            return False
        deadline = self.signup_deadline or self.starts_at
        return timezone.now() < deadline

    def can_manage(self, user) -> bool:
        return user.pk == self.organizer_id or user.is_officer_or_above

    def needs_for(self, role: str) -> int | None:
        return {Role.TANK: self.need_tanks, Role.HEAL: self.need_heals, Role.DPS: self.need_dps}[Role(role)]


class Signup(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="signups")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="signups")
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="signups")
    role = models.CharField("Rôle", max_length=8, choices=Role.choices)
    status = models.CharField(
        "Statut", max_length=8, choices=SignupStatus.choices, default=SignupStatus.PRESENT
    )
    comment = models.CharField("Commentaire", max_length=240, blank=True)
    placement = models.CharField(
        "Placement", max_length=10, choices=Placement.choices, default=Placement.UNPLACED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "inscription"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["event", "user"], name="one_signup_per_user_per_event")
        ]

    def __str__(self) -> str:
        return f"{self.character} → {self.event}"
