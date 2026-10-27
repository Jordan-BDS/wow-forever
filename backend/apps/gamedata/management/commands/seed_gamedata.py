from django.core.management.base import BaseCommand

from apps.gamedata.models import PlayerClass, Profession, Race, Specialization
from apps.gamedata.seed import seed


class Command(BaseCommand):
    help = "Pré-remplit (ou met à jour) les données de référence du jeu. Rejouable sans risque."

    def handle(self, *args, **options):
        seed()
        self.stdout.write(
            self.style.SUCCESS(
                f"{PlayerClass.objects.count()} classes, {Specialization.objects.count()} spécialisations, "
                f"{Race.objects.count()} races, {Profession.objects.count()} métiers."
            )
        )
