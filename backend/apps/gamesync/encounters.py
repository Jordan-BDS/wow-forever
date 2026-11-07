"""
Rencontres de raid vanilla (identifiant de rencontre → instance), lues dans la table DungeonEncounter du
client Forever (wago.tools, build 1.60.1.70862, 7 novembre 2026). Un identifiant inconnu est rangé dans
« Autres » avec le nom reçu de l'addon : les boss du monde (Kazzak, Azuregos, Thunderaan, dragons du
Cauchemar) et le raid inédit « Scarlet Enclave » y tombent pour l'instant. Les slugs sont ceux de
`gamedata.seed` (noms affichés).
"""

ENCOUNTERS: dict[int, tuple[str, int]] = {}


def _register(slug: str, ids: list[int]) -> None:
    for order, encounter_id in enumerate(ids):
        ENCOUNTERS[encounter_id] = (slug, order)


_register("onyxia", [1084])
_register("molten-core", [663, 664, 665, 666, 667, 668, 669, 670, 671, 672])
_register("upper-blackrock-spire", [3062, 3063, 3068, 3069])  # Emberseer, Rend, la Bête, Drakkisath
_register("blackwing-lair", [610, 611, 612, 613, 614, 615, 616, 617])
_register("zul-gurub", [785, 784, 786, 787, 788, 789, 790, 791, 792, 793])  # Hakkar = 793
_register("ruins-of-ahn-qiraj", [718, 719, 720, 721, 722, 723])
_register("temple-of-ahn-qiraj", [709, 710, 711, 712, 713, 714, 715, 716, 717])
# Dans l'ordre du client ; Kel'Thuzad = 1114 (1121 est les Quatre Cavaliers).
_register(
    "naxxramas", [1107, 1110, 1116, 1117, 1112, 1115, 1113, 1109, 1121, 1118, 1111, 1108, 1120, 1119, 1114]
)

INSTANCE_ORDER = [
    "onyxia",
    "molten-core",
    "upper-blackrock-spire",
    "zul-gurub",
    "blackwing-lair",
    "ruins-of-ahn-qiraj",
    "temple-of-ahn-qiraj",
    "naxxramas",
    "autres",
]

# Nombre de boss attendus par instance (barre d'avancement).
INSTANCE_SIZE = {
    slug: sum(1 for s, _ in ENCOUNTERS.values() if s == slug) for slug in INSTANCE_ORDER if slug != "autres"
}

#: Au moins autant de joueurs du site dans le groupe pour qu'un kill compte « pour la guilde ».
GUILD_KILL_MIN_MEMBERS = 5
