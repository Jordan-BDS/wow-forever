# Instantanés conservés : bases d'une complétion par le compagnon (7 novembre 2026).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gamesync", "0005_importbatch_errors"),
    ]

    operations = [
        migrations.AddField(
            model_name="charactersnapshot",
            name="kept",
            field=models.BooleanField(
                default=False,
                help_text="A servi de base à une complétion par le compagnon : jamais supprimé par le nettoyage.",
                verbose_name="Conservé",
            ),
        ),
    ]
