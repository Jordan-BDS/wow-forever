"""
Sortie du jeu (4 novembre 2026) : les personnages ne viennent plus que de l'addon. Tout ce qui avait été saisi à la
main avant la sortie est effacé, avec ses dépendances (métiers, sets, builds, recettes connues, inscriptions aux
événements) et l'historique d'import. Les appareils appairés du compagnon sont conservés.
"""

from django.db import migrations


def wipe(apps, schema_editor):
    for app, model in (
        ("gamesync", "WeeklyTitle"),
        ("gamesync", "CharacterSnapshot"),
        ("gamesync", "ImportBatch"),
        ("gamesync", "IgnoredCharacter"),
        ("characters", "Character"),
    ):
        apps.get_model(app, model).objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("gamesync", "0003_importbatch_client"),
        ("characters", "0004_sync_fields"),
        ("events", "0003_discord_sync"),
        ("crafting", "0001_initial"),
    ]

    operations = [migrations.RunPython(wipe, migrations.RunPython.noop)]
