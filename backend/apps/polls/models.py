import re

from django.conf import settings
from django.db import models
from django.utils import timezone


class FormatRule(models.TextChoices):
    FREE = "free", "Libre"
    GUILD_NAME = "guild_name", "Nom de guilde WoW"


class PollStatus(models.TextChoices):
    PROPOSALS = "proposals", "Propositions"
    VOTES = "votes", "Votes"
    CLOSED = "closed", "Clos"
    VALIDATED = "validated", "Validé"


# 2 à 24 caractères, lettres (accents compris) séparées par des espaces simples.
GUILD_NAME_RE = re.compile(r"^[^\W\d_]+(?: [^\W\d_]+)*$")


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


class Poll(models.Model):
    title = models.CharField("Titre", max_length=120)
    description = models.TextField("Description", blank=True)
    proposals_end = models.DateTimeField("Fin des propositions")
    votes_end = models.DateTimeField("Fin des votes")
    max_proposals_per_user = models.PositiveSmallIntegerField("Propositions max par personne", default=3)
    max_votes_per_user = models.PositiveSmallIntegerField(
        "Votes max par personne", null=True, blank=True, help_text="Vide = illimité"
    )
    format_rule = models.CharField(
        "Règle de format", max_length=16, choices=FormatRule.choices, default=FormatRule.FREE
    )
    sets_guild_name = models.BooleanField("Définit le nom de guilde", default=False)
    validated_proposal = models.OneToOneField(
        "Proposal", on_delete=models.SET_NULL, null=True, blank=True, related_name="won_poll"
    )
    validation_note = models.TextField("Justification de la validation", blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="polls_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "sondage"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def status(self) -> str:
        if self.validated_proposal_id:
            return PollStatus.VALIDATED
        now = timezone.now()
        if now >= self.votes_end:
            return PollStatus.CLOSED
        if now >= self.proposals_end:
            return PollStatus.VOTES
        return PollStatus.PROPOSALS

    @property
    def accepts_proposals(self) -> bool:
        return self.status == PollStatus.PROPOSALS

    @property
    def accepts_votes(self) -> bool:
        return self.status in (PollStatus.PROPOSALS, PollStatus.VOTES)

    def ranked_proposals(self):
        return self.proposals.annotate(vote_count=models.Count("votes")).order_by("-vote_count", "created_at")

    def validate_text(self, text: str) -> str | None:
        """Renvoie un message d'erreur si le texte ne respecte pas la règle de format."""
        if self.format_rule == FormatRule.GUILD_NAME:
            if not 2 <= len(text) <= 24:
                return "Un nom de guilde fait entre 2 et 24 caractères."
            if not GUILD_NAME_RE.match(text):
                return "Un nom de guilde ne contient que des lettres et des espaces simples."
        return None


class Proposal(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="proposals")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="proposals")
    text = models.CharField("Proposition", max_length=120)
    normalized_text = models.CharField(max_length=120, editable=False)
    note = models.CharField("Note", max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "proposition"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["poll", "normalized_text"], name="unique_proposal_text_per_poll"),
        ]

    def __str__(self) -> str:
        return self.text

    def save(self, *args, **kwargs):
        self.text = " ".join(self.text.split())
        self.normalized_text = normalize(self.text)
        super().save(*args, **kwargs)


class Vote(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="votes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "vote"
        constraints = [models.UniqueConstraint(fields=["proposal", "user"], name="one_vote_per_proposal")]

    def __str__(self) -> str:
        return f"{self.user} → {self.proposal}"
