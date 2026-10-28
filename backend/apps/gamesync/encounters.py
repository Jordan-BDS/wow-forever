"""
Rencontres de raid vanilla (identifiants de rencontre du client Classic → instance). À confirmer sur Forever ;
un identifiant inconnu est rangé dans « Autres » avec le nom reçu de l'addon.
"""

ENCOUNTERS: dict[int, tuple[str, int]] = {}


def _register(slug: str, ids: list[int]) -> None:
    for order, encounter_id in enumerate(ids):
        ENCOUNTERS[encounter_id] = (slug, order)


_register("onyxia", [1084])
_register("molten-core", [663, 664, 665, 666, 667, 668, 669, 670, 671, 672])
_register("blackwing-lair", [610, 611, 612, 613, 614, 615, 616, 617])
_register("zul-gurub", [784, 785, 786, 787, 788, 789, 790, 791, 792, 793, 796])
_register("ruins-of-ahnqiraj", [718, 719, 720, 721, 722, 723])
_register("temple-of-ahnqiraj", [709, 710, 711, 712, 713, 714, 715, 716, 717])
_register(
    "naxxramas", [1107, 1108, 1109, 1110, 1111, 1112, 1113, 1114, 1115, 1116, 1117, 1118, 1119, 1120, 1121]
)

INSTANCE_ORDER = [
    "onyxia",
    "molten-core",
    "zul-gurub",
    "blackwing-lair",
    "ruins-of-ahnqiraj",
    "temple-of-ahnqiraj",
    "naxxramas",
    "autres",
]

# Nombre de boss attendus par instance (barre d'avancement).
INSTANCE_SIZE = {
    slug: sum(1 for s, _ in ENCOUNTERS.values() if s == slug) for slug in INSTANCE_ORDER if slug != "autres"
}

#: Au moins autant de joueurs du site dans le groupe pour qu'un kill compte « pour la guilde ».
GUILD_KILL_MIN_MEMBERS = 5
