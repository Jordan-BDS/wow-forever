from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.gamedata import importer, wago


class Command(BaseCommand):
    help = (
        "Importe l'index du jeu (objets, sets, enchantements, talents, recettes) depuis les exports "
        "CSV des tables client. Télécharge depuis wago.tools si besoin. Rejouable."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--product", default=wago.DEFAULT_PRODUCT, help="Produit wago.tools (wowf, wow_classic_era…)"
        )
        parser.add_argument("--build", default="", help="Version précise, sinon la dernière du produit")
        parser.add_argument(
            "--dir", default="", help="Dossier contenant déjà les CSV (pas de téléchargement)"
        )
        parser.add_argument("--force-download", action="store_true", help="Retélécharge même si présent")

    def handle(self, *args, **options):
        if options["dir"]:
            directory = Path(options["dir"])
            build, product = options["build"] or directory.name, options["product"]
        else:
            product = options["product"]
            build = options["build"] or wago.latest_build(product)
            directory = Path(settings.BASE_DIR) / "data" / "wago" / product / build
            self.stdout.write(f"Données {product} {build} → {directory}")
            downloaded = wago.download_tables(build, directory, force=options["force_download"])
            self.stdout.write(f"{len(downloaded)} table(s) téléchargée(s)")

        missing = importer.missing_tables(directory)
        if missing:
            raise CommandError(f"Tables manquantes dans {directory} : {', '.join(missing)}")

        run = importer.import_directory(directory, build=build, product=product)
        summary = ", ".join(f"{value} {key}" for key, value in run.counts.items())
        self.stdout.write(self.style.SUCCESS(f"Import terminé ({build}) : {summary}"))
