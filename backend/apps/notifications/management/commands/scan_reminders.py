"""
Balayage des tâches dues (titres du lundi, rappels d'événements et de sondages, suivi Discord des sondages),
le même que celui du bot Discord toutes les 60 s. Filet de sécurité pour le cas où le bot est arrêté : les
tâches marquent ce qu'elles ont fait, donc les deux peuvent tourner en même temps sans doublon. Ce balayage ne
parle pas à Discord : il remplit la file d'envoi, que le bot vide quand il tourne.
"""

from __future__ import annotations

import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.notifications.reminders import scan_due_reminders

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Balaye les tâches dues une fois, ou en boucle avec --loop (service « scheduler » du compose)."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Boucler toutes les --interval s")
        parser.add_argument("--interval", type=int, default=300, help="Secondes entre deux balayages (300)")

    def handle(self, *args, **options):
        interval = max(10, options["interval"])
        while True:
            try:
                created = scan_due_reminders()
                if created:
                    self.stdout.write(f"{created} tâche(s) traitée(s)")
            except Exception:  # noqa: BLE001 — en boucle, une erreur ne doit pas tuer le service
                if not options["loop"]:
                    raise
                logger.exception("Échec du balayage des rappels")
            if not options["loop"]:
                return
            close_old_connections()
            time.sleep(interval)
