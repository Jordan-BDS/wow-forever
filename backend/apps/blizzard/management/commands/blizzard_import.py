from django.core.management.base import BaseCommand, CommandError

from apps.blizzard import services
from apps.blizzard.client import BlizzardError


class Command(BaseCommand):
    help = (
        "Lit sur l'API Battle.net tous les personnages du site qui ont un nom de famille, et la guilde, et "
        "archive chaque réponse (une lecture par passage : c'est l'historique). Rejouable, à planifier une "
        "fois par jour."
    )

    def handle(self, *args, **options):
        try:
            client = services.client_from_settings()
            counts = services.fetch_all(client)
        except BlizzardError as exc:
            raise CommandError(f"API Battle.net : {exc}") from exc
        summary = (
            f"{counts['characters']} personnage(s) : {counts['found']} lu(s), {counts['missing']} inconnu(s) "
            f"de l'API ; guilde : {counts['guild']} réponse(s) ; {counts['records']} lecture(s) archivée(s), "
            f"{client.calls} appel(s)"
        )
        self.stdout.write(self.style.SUCCESS(summary))
