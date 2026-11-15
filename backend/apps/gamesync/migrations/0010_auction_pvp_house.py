from django.db import migrations, models

PVP_HOUSE = "PvP"


def merge_pvp_houses(apps, schema_editor):
    """Tout hôtel dont le nom contient « pvp » devient l'hôtel « PvP » : même jeu de règles, même hôtel. Deux
    scans du même instant ne peuvent pas coexister dans un hôtel : le premier reçu reste."""
    AuctionScan = apps.get_model("gamesync", "AuctionScan")
    taken = set(AuctionScan.objects.filter(house=PVP_HOUSE).values_list("scanned_at", flat=True))
    scans = AuctionScan.objects.exclude(house=PVP_HOUSE).order_by("received_at", "pk")
    for scan in scans.only("pk", "house", "scanned_at"):
        if "pvp" not in scan.house.lower():
            continue
        if scan.scanned_at in taken:
            scan.delete()
            continue
        taken.add(scan.scanned_at)
        AuctionScan.objects.filter(pk=scan.pk).update(house=PVP_HOUSE)


class Migration(migrations.Migration):
    dependencies = [
        ("gamesync", "0009_favorite_recipes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auctionscan",
            name="house",
            field=models.CharField(
                help_text="« PvP » pour tout hôtel dont le nom contient « pvp », sinon le nom écrit par l'addon.",
                max_length=96,
                verbose_name="Hôtel des ventes",
            ),
        ),
        # Sans retour : les noms d'origine ne sont pas gardés.
        migrations.RunPython(merge_pvp_houses, migrations.RunPython.noop),
    ]
