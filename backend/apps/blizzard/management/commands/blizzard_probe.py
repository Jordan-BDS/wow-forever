from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.blizzard import services
from apps.blizzard.client import BlizzardError


class Command(BaseCommand):
    help = (
        "Sonde l'API Battle.net de WoW Forever : lit la fiche d'un personnage (prénom-nom) et ses "
        "sous-ressources, ou la guilde, affiche le statut et les clés de chaque réponse, les archive et les "
        "écrit en JSON dans data/blizzard/ pour en fixer la forme avant d'écrire l'import."
    )

    def add_arguments(self, parser):
        parser.add_argument("--character", default="", help="Personnage, ex. thrall-fils-de-durotan")
        parser.add_argument(
            "--guild", default="", help="Guilde, ex. manuel-feralas (défaut : Guilde › Paramètres)"
        )
        parser.add_argument("--no-guild", action="store_true", help="Ne pas lire la guilde")
        parser.add_argument("--dir", default="", help="Dossier des JSON (défaut : backend/data/blizzard)")

    def handle(self, *args, **options):
        try:
            client = services.client_from_settings()
        except BlizzardError as exc:
            raise CommandError(str(exc)) from exc
        directory = Path(options["dir"] or Path(settings.BASE_DIR) / "data" / "blizzard")
        records = []
        try:
            status, rulesets = client.rulesets()
            self.stdout.write(f"rulesets (dynamic) : {status} · {services.describe(rulesets)}")
            if options["character"]:
                records += services.fetch_character(client, options["character"].strip().lower())
            if not options["no_guild"]:
                slug = options["guild"].strip().lower() or services.guild_slug()
                if slug:
                    records += services.fetch_guild(client, slug)
                else:
                    self.stdout.write("guilde : aucun nom dans Guilde › Paramètres, passe --guild")
        except BlizzardError as exc:
            raise CommandError(f"API Battle.net : {exc}") from exc
        for record in records:
            style = self.style.SUCCESS if record.http_status == 200 else self.style.WARNING
            self.stdout.write(
                style(
                    f"{record.kind} {record.slug} : {record.http_status} · {services.describe(record.data)}"
                )
            )
        written = services.dump(records, directory)
        self.stdout.write(
            f"{len(records)} réponse(s) archivée(s), {client.calls} appel(s) ; JSON dans {directory}"
        )
        if written:
            self.stdout.write("Envoie ce dossier (ou les clés ci-dessus) pour écrire l'import.")
