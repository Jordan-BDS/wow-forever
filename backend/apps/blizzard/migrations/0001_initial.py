# Archive brute des lectures de l'API Battle.net (7 novembre 2026).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("characters", "0004_sync_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="BlizzardRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(db_index=True, max_length=40)),
                ("slug", models.CharField(db_index=True, max_length=80)),
                ("fetched_at", models.DateTimeField(auto_now_add=True)),
                (
                    "http_status",
                    models.PositiveSmallIntegerField(
                        help_text="200 : lu ; 404 : la ressource n'existe pas (encore)."
                    ),
                ),
                ("data", models.JSONField(blank=True, default=dict)),
                (
                    "character",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="blizzard_records",
                        to="characters.character",
                    ),
                ),
            ],
            options={
                "verbose_name": "lecture Battle.net",
                "verbose_name_plural": "lectures Battle.net",
                "ordering": ["-fetched_at"],
                "indexes": [
                    models.Index(fields=["kind", "slug", "fetched_at"], name="blizzard_bl_kind_ca7d97_idx")
                ],
            },
        ),
    ]
