"""
Titres de la semaine : calculés le lundi à partir de 10h (Europe/Paris) sur les données horodatées avant lundi
00h00, puis figés. Un récapitulatif part dans le salon général par l'outbox du bot.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import Notification, NotificationKind

from .models import WeeklyTitle
from .progress import latest_snapshots
from .rankings import CATEGORY_BY_KEY, WEEKLY_TITLES, category_entries
from .services import PARIS

AWARD_HOUR = 10


def format_value(key: str, value: float) -> str:
    unit = {
        "gathering.mining": "minerais",
        "bg_won": "BG gagnés",
        "boss_kills": "boss",
        "deaths": "morts",
    }.get(key, "")
    number = int(value) if float(value).is_integer() else value
    return f"{number} {unit}".strip()


@transaction.atomic
def award_weekly_titles(now: datetime | None = None) -> list[WeeklyTitle]:
    """Attribue les titres de la semaine close si l'heure est venue et que ce n'est pas déjà fait."""
    now = now or timezone.now()
    local = now.astimezone(PARIS)
    this_monday = local.date() - timedelta(days=local.weekday())
    if local < datetime.combine(this_monday, time(AWARD_HOUR), tzinfo=PARIS):
        return []
    week_start = this_monday - timedelta(days=7)
    if WeeklyTitle.objects.filter(week_start=week_start).exists():
        return []
    snapshots = latest_snapshots()
    created: list[WeeklyTitle] = []
    for key, label, category_key in WEEKLY_TITLES:
        entries = category_entries(
            CATEGORY_BY_KEY[category_key], snapshots, "player", week_start, this_monday - timedelta(days=1)
        )
        if not entries or entries[0].value <= 0:
            continue
        best = entries[0]
        created.append(
            WeeklyTitle.objects.create(
                week_start=week_start,
                key=key,
                label=label,
                user_id=best.user_id,
                character_id=best.character_id,
                value=best.value,
            )
        )
    if created:
        counter_by_title = {
            key: CATEGORY_BY_KEY[category].counter or category for key, _, category in WEEKLY_TITLES
        }
        week_end = week_start + timedelta(days=6)
        span = f"{week_start.strftime('%d/%m')} → {week_end.strftime('%d/%m')}"
        lines = [f"🏆 **Roxors de la semaine passée** ({span})"]
        for title in created:
            perso = f" ({title.character.name})" if title.character else ""
            value = format_value(counter_by_title[title.key], title.value)
            lines.append(f"• {title.label} : **{title.user.display_name}**{perso} — {value}")
        lines.append("Classements complets sur le site, page Classements.")
        Notification.objects.create(kind=NotificationKind.WEEKLY_RECAP, text="\n".join(lines))
    return created
