"""Règles vanilla des talents, côté serveur (miroir de frontend/src/lib/talents.ts)."""

from collections import defaultdict

from apps.gamedata.models import Specialization, Talent, TalentTree

MAX_POINTS = 51
POINTS_PER_TIER = 5
FIRST_TALENT_LEVEL = 10


def acquired_points(level: int) -> int:
    return max(0, min(MAX_POINTS, level - FIRST_TALENT_LEVEL + 1))


def validate_order(points: list[int], class_slug: str) -> str | None:
    """
    Rejoue l'attribution des points dans l'ordre. Renvoie un message d'erreur si une étape est invalide :
    talent inconnu ou d'une autre classe, rang max dépassé, rangée verrouillée,
    prérequis manquant, plus de 51 points.
    """
    if len(points) > MAX_POINTS:
        return f"Au plus {MAX_POINTS} points."
    talents = {
        t.id: t for t in Talent.objects.filter(tree__player_class__slug=class_slug).select_related("tree")
    }
    ranks: dict[int, int] = defaultdict(int)
    for step, talent_id in enumerate(points, start=1):
        talent = talents.get(talent_id)
        if talent is None:
            return f"Point {step} : talent inconnu pour cette classe."
        if ranks[talent_id] >= talent.max_rank:
            return f"Point {step} : {talent.name} est déjà au rang maximum."
        above = sum(
            ranks[t.id] for t in talents.values() if t.tree_id == talent.tree_id and t.row < talent.row
        )
        if above < POINTS_PER_TIER * talent.row:
            return f"Point {step} : la rangée de {talent.name} n'est pas encore débloquée."
        if talent.prerequisite_id:
            required = talent.prerequisite_rank or talents[talent.prerequisite_id].max_rank
            if ranks[talent.prerequisite_id] < required:
                return (
                    f"Point {step} : {talent.name} requiert d'abord {talents[talent.prerequisite_id].name}."
                )
        ranks[talent_id] += 1
    return None


def dominant_tree(points: list[int]) -> TalentTree | None:
    if not points:
        return None
    counts: dict[int, int] = defaultdict(int)
    for talent in Talent.objects.filter(id__in=set(points)).only("id", "tree_id"):
        counts[talent.tree_id] += points.count(talent.id)
    if not counts:
        return None
    best = max(counts, key=lambda tree_id: (counts[tree_id], -tree_id))
    return TalentTree.objects.select_related("player_class").get(pk=best)


def specialization_for(tree: TalentTree | None) -> Specialization | None:
    """Spécialisation (donnée de référence) correspondant à un arbre : même classe, même ordre."""
    if tree is None:
        return None
    return Specialization.objects.filter(player_class=tree.player_class, order=tree.order).first()
