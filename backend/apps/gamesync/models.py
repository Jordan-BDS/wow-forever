"""
Synchronisation depuis le jeu : appairage du compagnon, archive brute des imports, instantanés par personnage.
Les règles sont décrites au cahier des charges, étape 11.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class PairingCode(models.Model):
    """Code à 6 caractères affiché sur le site, saisi dans le compagnon, échangé contre un jeton."""

    LIFETIME_MINUTES = 10
    ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O ni 1/I
    LENGTH = 6

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pairing_codes")
    code = models.CharField(max_length=8, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "code d'appairage"

    def __str__(self) -> str:
        return f"{self.code} ({self.user})"


class CompanionDevice(models.Model):
    """Une installation du compagnon sur une machine ; le jeton n'est stocké que haché."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="companions")
    name = models.CharField("Machine", max_length=64)
    token_hash = models.CharField(max_length=64, unique=True)
    token_prefix = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "compagnon"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.user})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class ImportSource(models.TextChoices):
    PASTE = "paste", "Collage sur le site"
    COMPANION = "companion", "Compagnon"


class ImportBatch(models.Model):
    """Un code d'export accepté, conservé tel quel : les imports sont rejouables."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="import_batches"
    )
    device = models.ForeignKey(CompanionDevice, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(max_length=16, choices=ImportSource.choices)
    fingerprint = models.CharField(max_length=64, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)
    format_version = models.PositiveSmallIntegerField()
    addon_version = models.CharField(max_length=32, blank=True)
    install_id = models.CharField(max_length=64, blank=True)
    client = models.CharField(
        "Client de jeu",
        max_length=64,
        blank=True,
        help_text="Version et numéro d'interface du client, ex. « 12.1.5 (120105) ».",
    )
    code = models.TextField(help_text="Le code d'export tel que reçu.")
    summary = models.JSONField(default=dict)
    errors = models.JSONField(
        default=list,
        blank=True,
        help_text="Erreurs des collecteurs de l'addon, telles qu'exportées (t, where, error, addon).",
    )

    class Meta:
        verbose_name = "import"
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"Import {self.pk} de {self.user} ({self.source})"


class SnapshotStatus(models.TextChoices):
    APPLIED = "applied", "Mis à jour"
    CREATED = "created", "Créé"
    PENDING = "pending", "À rattacher"
    IGNORED = "ignored", "Ignoré"
    STALE = "stale", "Plus ancien que le dernier import"
    REFUSED = "refused", "Refusé"


class CharacterSnapshot(models.Model):
    """L'état d'un personnage dans un code d'export, et ce que le site en a fait."""

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="snapshots")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    character = models.ForeignKey(
        "characters.Character", on_delete=models.SET_NULL, null=True, blank=True, related_name="snapshots"
    )
    candidate = models.ForeignKey(
        "characters.Character",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Personnage du site proposé pour la fusion (statut « à rattacher »).",
    )
    guid = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=24)
    surname = models.CharField(max_length=24, blank=True)
    realm = models.CharField(max_length=64, blank=True)
    exported_at = models.DateTimeField()
    day = models.DateField(help_text="Jour de l'export en Europe/Paris (un instantané conservé par jour).")
    data = models.JSONField()
    status = models.CharField(max_length=10, choices=SnapshotStatus.choices)
    note = models.CharField(max_length=200, blank=True)
    kept = models.BooleanField(
        "Conservé",
        default=False,
        help_text="A servi de base à une complétion par le compagnon : jamais supprimé par le nettoyage.",
    )

    class Meta:
        verbose_name = "instantané de personnage"
        ordering = ["-exported_at"]
        indexes = [models.Index(fields=["character", "day"])]

    def __str__(self) -> str:
        return f"{self.full_name} — {self.get_status_display()}"

    @property
    def full_name(self) -> str:
        return f"{self.name} {self.surname}".strip()


class IgnoredCharacter(models.Model):
    """Personnage du jeu que le joueur ne veut pas voir sur le site (alt banque…)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ignored_characters"
    )
    guid = models.CharField(max_length=64)
    name = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "personnage ignoré"
        constraints = [models.UniqueConstraint(fields=["user", "guid"], name="unique_ignored_guid_per_user")]

    def __str__(self) -> str:
        return f"{self.name or self.guid} ({self.user})"


class WeeklyTitle(models.Model):
    """Titre de la semaine, attribué dès lundi minuit sur la semaine close, jamais remis en cause."""

    week_start = models.DateField(help_text="Lundi de la semaine récompensée.")
    key = models.CharField(max_length=32)
    label = models.CharField(max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weekly_titles")
    character = models.ForeignKey(
        "characters.Character", on_delete=models.SET_NULL, null=True, blank=True, related_name="weekly_titles"
    )
    value = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "titre de la semaine"
        ordering = ["-week_start", "key"]
        constraints = [models.UniqueConstraint(fields=["week_start", "key"], name="unique_title_per_week")]

    def __str__(self) -> str:
        return f"{self.label} — semaine du {self.week_start} : {self.user}"


class AuctionScan(models.Model):
    """Un scan complet d'un hôtel des ventes, envoyé par un compagnon : un par hôtel et par instant."""

    house = models.CharField(
        "Hôtel des ventes",
        max_length=96,
        help_text="« PvP » pour tout hôtel dont le nom contient « pvp », sinon le nom écrit par l'addon.",
    )
    scanned_at = models.DateTimeField("Scanné le")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auction_scans")
    device = models.ForeignKey(CompanionDevice, on_delete=models.SET_NULL, null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    items = models.PositiveIntegerField("Objets", default=0)

    class Meta:
        verbose_name = "scan de l'hôtel des ventes"
        verbose_name_plural = "scans de l'hôtel des ventes"
        ordering = ["-scanned_at"]
        constraints = [
            models.UniqueConstraint(fields=["house", "scanned_at"], name="unique_auction_scan_per_house")
        ]

    def __str__(self) -> str:
        return f"{self.house} — {self.scanned_at:%d/%m/%Y %H:%M}"


class AuctionReport(models.Model):
    """Ce qu'un compagnon a fait d'un fichier de scan de l'hôtel des ventes (Auctionator, NaowhForever) :
    envoyé, rien de nouveau, illisible et pourquoi. Le même constat répété ne fait qu'une ligne (`count`,
    `at`). Pour le GM, page Tests."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auction_reports"
    )
    device = models.ForeignKey(CompanionDevice, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField("Addon lu", max_length=32)
    house = models.CharField("Hôtel ou royaume", max_length=96, blank=True)
    kind = models.CharField("Résultat", max_length=24)
    detail = models.TextField("Détail", blank=True)
    day = models.IntegerField("Jour d'Auctionator", null=True, blank=True)
    items = models.PositiveIntegerField("Objets", null=True, blank=True)
    scanned_at = models.DateTimeField("Scan daté du", null=True, blank=True)
    file_at = models.DateTimeField("Fichier écrit le", null=True, blank=True)
    companion = models.CharField("Version du compagnon", max_length=24, blank=True)
    first_at = models.DateTimeField(auto_now_add=True)
    at = models.DateTimeField("Dernier constat")
    count = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "rapport d'envoi de l'hôtel des ventes"
        verbose_name_plural = "rapports d'envoi de l'hôtel des ventes"
        ordering = ["-at"]
        indexes = [models.Index(fields=["user", "source", "house", "at"], name="auction_report_lookup")]

    def __str__(self) -> str:
        return f"{self.source} {self.house} : {self.kind}"


class AuctionPrice(models.Model):
    """Le prix le plus bas d'un objet dans un scan (à l'unité, en cuivre) et le nombre d'enchères."""

    scan = models.ForeignKey(AuctionScan, on_delete=models.CASCADE, related_name="prices")
    item_id = models.PositiveIntegerField()
    price = models.PositiveBigIntegerField(help_text="Prix le plus bas à l'unité, en cuivre.")
    listed = models.PositiveIntegerField(
        null=True, blank=True, help_text="Nombre d'enchères avec achat immédiat."
    )

    class Meta:
        verbose_name = "prix de l'hôtel des ventes"
        constraints = [
            models.UniqueConstraint(fields=["scan", "item_id"], name="unique_item_per_auction_scan")
        ]
        indexes = [models.Index(fields=["item_id", "scan"])]

    def __str__(self) -> str:
        return f"{self.item_id} : {self.price}"


class FavoriteRecipe(models.Model):
    """Recette suivie par un joueur sur la page de l'hôtel des ventes (coût des composants, bénéfice)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorite_recipes"
    )
    recipe = models.ForeignKey("gamedata.Recipe", on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "recette favorite"
        verbose_name_plural = "recettes favorites"
        constraints = [models.UniqueConstraint(fields=["user", "recipe"], name="unique_favorite_recipe")]

    def __str__(self) -> str:
        return f"{self.user} suit {self.recipe}"


class FavoriteItem(models.Model):
    """Objet suivi par un joueur sur la page de l'hôtel des ventes. L'objet est nommé par son ID seul : un
    objet en vente peut manquer à l'index du site. Le joueur peut y poser deux seuils : il est prévenu quand
    le prix le plus bas passe à son prix d'achat ou en dessous, à son prix de vente ou au-dessus."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorite_items"
    )
    item_id = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    buy_price = models.PositiveBigIntegerField(
        "Prix d'achat", null=True, blank=True, help_text="En cuivre : alerte à ce prix ou en dessous."
    )
    sell_price = models.PositiveBigIntegerField(
        "Prix de vente", null=True, blank=True, help_text="En cuivre : alerte à ce prix ou au-dessus."
    )
    # Le seuil était franchi au dernier scan regardé : l'alerte ne repart qu'après un retour de l'autre côté.
    buy_hit = models.BooleanField(default=False)
    sell_hit = models.BooleanField(default=False)

    class Meta:
        verbose_name = "objet favori"
        verbose_name_plural = "objets favoris"
        constraints = [models.UniqueConstraint(fields=["user", "item_id"], name="unique_favorite_item")]

    def __str__(self) -> str:
        return f"{self.user} suit l'objet {self.item_id}"


class AuctionTrade(models.Model):
    """Un achat ou une vente d'un joueur à l'hôtel des ventes, noté par l'addon (`Collectors/Trades.lua`) et
    reçu avec l'export. Privé : chacun ne voit que les siens, sur la courbe de prix de l'objet. Gardé sans
    limite de durée. L'addon numérote ses entrées par installation (`seq`) : la même entrée renvoyée,
    complétée entre-temps (nom, objet d'un achat lu dans le courrier), met la ligne à jour."""

    BUY, SELL = "buy", "sell"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auction_trades"
    )
    install_id = models.CharField("Installation de l'addon", max_length=64)
    seq = models.PositiveIntegerField("Numéro dans l'installation")
    at = models.DateTimeField("Le")
    kind = models.CharField("Sens", max_length=4, choices=[(BUY, "Achat"), (SELL, "Vente")])
    source = models.CharField(
        "Noté par", max_length=12, blank=True, help_text="bid, commodity ou mail : voir l'addon."
    )
    item_id = models.PositiveIntegerField(
        null=True, blank=True, help_text="Vide : une vente dont le nom ne désigne aucun objet de l'index."
    )
    name = models.CharField("Nom dans le jeu", max_length=120, blank=True)
    quantity = models.PositiveIntegerField(
        "Quantité", null=True, blank=True, help_text="Vide : la facture d'une vente ne la donnait pas."
    )
    price = models.PositiveBigIntegerField("Prix à l'unité", null=True, blank=True, help_text="En cuivre.")
    total = models.PositiveBigIntegerField("Total", help_text="En cuivre, commission non déduite.")
    fee = models.PositiveBigIntegerField("Commission", default=0)
    deposit = models.PositiveBigIntegerField("Dépôt", default=0)
    character_guid = models.CharField(max_length=64, blank=True)
    realm = models.CharField(max_length=96, blank=True)
    house = models.CharField("Hôtel des ventes", max_length=96, blank=True)
    faction = models.CharField(max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "transaction à l'hôtel des ventes"
        verbose_name_plural = "transactions à l'hôtel des ventes"
        ordering = ["at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "install_id", "seq"], name="unique_auction_trade")
        ]
        indexes = [models.Index(fields=["user", "item_id", "at"], name="auction_trade_lookup")]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.name or self.item_id} : {self.total}"


class WantedExclusion(models.Model):
    """Nom retiré du tableau Wanted par le GM (PNJ homonyme pris pour un joueur, erreur de lecture)."""

    name = models.CharField(
        "Nom", max_length=64, unique=True, help_text="Tel que l'addon l'a lu ; la casse ne compte pas."
    )
    reason = models.CharField("Raison", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "nom retiré du tableau Wanted"
        verbose_name_plural = "noms retirés du tableau Wanted"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.name = " ".join(self.name.split()).lower()
        super().save(*args, **kwargs)


class Bounty(models.Model):
    """Prime posée à la main par un membre sur un joueur adverse, ou sur une guilde adverse (`is_guild` :
    chaque membre abattu compte) : tant par kill, pour un nombre de kills au plus. Les kills sont lus dans les
    événements `pk` exportés par l'addon (`bounties.py`), pas stockés."""

    poster = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bounties")
    addon_id = models.CharField(
        "Identifiant en jeu",
        max_length=40,
        blank=True,
        help_text="Celui que l'addon a donné à une prime posée en jeu ; vide si elle est posée sur le site.",
    )
    target_name = models.CharField("Cible", max_length=64)
    target_key = models.CharField(max_length=64, db_index=True, editable=False)
    is_guild = models.BooleanField(
        "Prime de guilde",
        default=False,
        help_text="La cible est une guilde adverse : chaque membre abattu compte pour un kill.",
    )
    amount = models.PositiveBigIntegerField("Or par kill (en cuivre)", default=0)
    item = models.ForeignKey(
        "gamedata.Item", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    item_count = models.PositiveIntegerField("Objets par kill", default=0)
    max_kills = models.PositiveIntegerField("Kills payés au plus", default=1)
    note = models.CharField("Mot du commanditaire", max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "prime"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["addon_id"], condition=~models.Q(addon_id=""), name="unique_bounty_addon_id"
            )
        ]

    def __str__(self) -> str:
        return f"Prime de {self.poster} sur {'la guilde ' if self.is_guild else ''}{self.target_name}"

    def save(self, *args, **kwargs):
        self.target_name = " ".join(self.target_name.split())
        self.target_key = self.target_name.lower()
        super().save(*args, **kwargs)


class BountyPayment(models.Model):
    """Ce que le commanditaire d'une prime déclare avoir remis à un chasseur. Le paiement se fait en jeu : le
    site ne le voit pas, il tient les comptes."""

    bounty = models.ForeignKey(Bounty, on_delete=models.CASCADE, related_name="payments")
    hunter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bounty_payments"
    )
    amount = models.PositiveBigIntegerField("Or remis (en cuivre)", default=0)
    item_count = models.PositiveIntegerField("Objets remis", default=0)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "paiement de prime"
        verbose_name_plural = "paiements de primes"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.bounty} : payé à {self.hunter}"
