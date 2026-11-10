"""Règles vanilla des talents, côté serveur (miroir de frontend/src/lib/talents.ts)."""

from collections import defaultdict

from apps.gamedata.models import Specialization, Talent, TalentTree

from .models import TalentBuild

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
        if error := _step_error(talent_id, talents, ranks):
            return f"Point {step} : {error}"
        ranks[talent_id] += 1
    return None


def _step_error(talent_id: int, talents: dict[int, Talent], ranks: dict[int, int]) -> str | None:
    """Pourquoi un point de plus dans ce talent est refusé, vu les rangs déjà posés ; None s'il est permis."""
    talent = talents.get(talent_id)
    if talent is None:
        return "talent inconnu pour cette classe."
    if ranks[talent_id] >= talent.max_rank:
        return f"{talent.name} est déjà au rang maximum."
    above = sum(ranks[t.id] for t in talents.values() if t.tree_id == talent.tree_id and t.row < talent.row)
    if above < POINTS_PER_TIER * talent.row:
        return f"la rangée de {talent.name} n'est pas encore débloquée."
    if talent.prerequisite_id:
        required = talent.prerequisite_rank or talents[talent.prerequisite_id].max_rank
        if ranks[talent.prerequisite_id] < required:
            return f"{talent.name} requiert d'abord {talents[talent.prerequisite_id].name}."
    return None


def prune_points(points: list[int], talents: dict[int, Talent]) -> list[int]:
    """Les points d'un build qui tiennent encore dans l'index, dans leur ordre : un point que les règles
    refusent (talent retiré, rang max baissé, talent déplacé) est remis en jeu tant que d'autres points
    passent, puis abandonné s'il ne passe toujours pas."""
    kept: list[int] = []
    ranks: dict[int, int] = defaultdict(int)
    pending = list(points)[:MAX_POINTS]
    while pending:
        refused = []
        for talent_id in pending:
            if _step_error(talent_id, talents, ranks):
                refused.append(talent_id)
            else:
                ranks[talent_id] += 1
                kept.append(talent_id)
        if len(refused) == len(pending):
            break
        pending = refused
    return kept


def prune_builds() -> int:
    """Après un import de l'index : retire des builds enregistrés les points qui n'y tiennent plus. Renvoie le
    nombre de builds modifiés."""
    by_class: dict[int, dict[int, Talent]] = defaultdict(dict)
    for talent in Talent.objects.select_related("tree"):
        by_class[talent.tree.player_class_id][talent.id] = talent
    changed = 0
    for build in TalentBuild.objects.select_related("character"):
        points = prune_points(build.points, by_class[build.character.player_class_id])
        if points != build.points:
            build.points = points
            build.save(update_fields=["points", "updated_at"])
            changed += 1
    return changed


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
