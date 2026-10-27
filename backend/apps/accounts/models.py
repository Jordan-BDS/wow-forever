from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class SiteRole(models.TextChoices):
    MEMBER = "member", "Membre"
    OFFICER = "officer", "Officier"
    GM = "gm", "GM"


ROLE_RANK = {SiteRole.MEMBER: 0, SiteRole.OFFICER: 1, SiteRole.GM: 2}


class DeactivationReason(models.TextChoices):
    DISCORD = "discord", "Rôle Discord perdu ou départ du serveur"
    MANUAL = "manual", "Désactivé par un officier"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, discord_id: str, **extra_fields):
        if not discord_id:
            raise ValueError("L'ID Discord est obligatoire")
        extra_fields.setdefault("discord_username", discord_id)
        extra_fields.setdefault("display_name", extra_fields["discord_username"])
        user = self.model(discord_id=discord_id, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, discord_id: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("site_role", SiteRole.GM)
        user = self.create_user(discord_id, **extra_fields)
        if password:
            user.set_password(password)
            user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """Un membre de la guilde. L'identité vient de Discord, le rôle du site est géré ici."""

    discord_id = models.CharField("ID Discord", max_length=32, unique=True)
    discord_username = models.CharField("Pseudo Discord", max_length=64)
    discord_avatar = models.CharField("Hash d'avatar Discord", max_length=128, blank=True)
    display_name = models.CharField("Nom affiché", max_length=64)
    bio = models.TextField("Bio", blank=True)
    site_role = models.CharField(
        "Rôle sur le site", max_length=16, choices=SiteRole.choices, default=SiteRole.MEMBER
    )
    is_active = models.BooleanField("Actif", default=True)
    deactivation_reason = models.CharField(
        "Motif de désactivation", max_length=16, choices=DeactivationReason.choices, blank=True
    )
    is_staff = models.BooleanField("Accès à l'admin Django", default=False)
    date_joined = models.DateTimeField("Première connexion", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "discord_id"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "membre"
        verbose_name_plural = "membres"
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name or self.discord_username

    @property
    def avatar_url(self) -> str:
        if self.discord_avatar:
            ext = "gif" if self.discord_avatar.startswith("a_") else "png"
            return (
                f"https://cdn.discordapp.com/avatars/{self.discord_id}/{self.discord_avatar}.{ext}?size=128"
            )
        index = (int(self.discord_id) >> 22) % 6 if self.discord_id.isdigit() else 0
        return f"https://cdn.discordapp.com/embed/avatars/{index}.png"

    @property
    def role_rank(self) -> int:
        return ROLE_RANK[SiteRole(self.site_role)]

    @property
    def is_officer_or_above(self) -> bool:
        return self.role_rank >= ROLE_RANK[SiteRole.OFFICER]

    @property
    def is_gm(self) -> bool:
        return self.site_role == SiteRole.GM

    def outranks(self, other: "User") -> bool:
        return self.role_rank > other.role_rank
