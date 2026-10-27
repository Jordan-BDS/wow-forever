from django.core.management.base import BaseCommand

from apps.discordbot.bot import run


class Command(BaseCommand):
    help = "Lance le bot Discord (notifications, rappels, commandes slash, révocation d'accès)."

    def handle(self, *args, **options):
        self.stdout.write("Démarrage du bot Discord…")
        run()
