"""
Archive brute des réponses de l'API Battle.net, une ligne par lecture : comme pour les exports de l'addon,
tout ce que le site en tirera plus tard se recalcule depuis le JSON tel que reçu (rejouable). C'est aussi
l'historique : une lecture par jour et par personnage donne les différences par période.
"""

from django.db import models


class BlizzardRecord(models.Model):
    #: `character/profile`, `character/statistics`, `guild/roster`… (le chemin après le slug, ou `profile`).
    kind = models.CharField(max_length=40, db_index=True)
    #: `prénom-nom` du personnage ou slug de la guilde, tel qu'envoyé à l'API.
    slug = models.CharField(max_length=80, db_index=True)
    character = models.ForeignKey(
        "characters.Character",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blizzard_records",
    )
    fetched_at = models.DateTimeField(auto_now_add=True)
    http_status = models.PositiveSmallIntegerField(
        help_text="200 : lu ; 404 : la ressource n'existe pas (encore)."
    )
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "lecture Battle.net"
        verbose_name_plural = "lectures Battle.net"
        ordering = ["-fetched_at"]
        indexes = [models.Index(fields=["kind", "slug", "fetched_at"])]

    def __str__(self) -> str:
        return f"{self.kind} {self.slug} ({self.http_status}) {self.fetched_at:%d/%m %H:%M}"
