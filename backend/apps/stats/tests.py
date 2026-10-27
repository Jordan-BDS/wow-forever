import pytest

from apps.gamedata.models import Enchantment, Item, ItemSet
from apps.stats.engine import SlotInput, compute

pytestmark = pytest.mark.django_db


def test_sums_items_enchantments_and_reports_projected_slots():
    ring = Item.objects.create(id=1, name="Anneau", stats={"stamina": 8, "strength": 5})
    sword = Item.objects.create(id=2, name="Épée", stats={"agility": 5, "stamina": 8}, required_level=60)
    crusader = Enchantment.objects.create(id=10, name="Croisé", stats={"strength": 15})
    result = compute(
        [
            SlotInput("finger1", ring),
            SlotInput("main_hand", sword, crusader),
            SlotInput(
                "head", Item.objects.create(id=3, name="Casque", stats={"stamina": 20}), projected=True
            ),
            SlotInput("neck", None),
        ]
    )
    assert result.totals == {"strength": 20, "agility": 5, "stamina": 16}
    assert result.breakdown["strength"] == {"items": 5, "enchantments": 15}
    assert result.projected_slots == ["head"]
    assert list(result.totals) == ["strength", "agility", "stamina"]  # ordre canonique


def test_set_bonuses_activate_by_piece_count():
    item_set = ItemSet.objects.create(
        id=5,
        name="Armure volcanique",
        bonuses=[
            {"threshold": 2, "spell_id": 1, "description": "+x"},
            {"threshold": 3, "spell_id": 2, "description": "+y"},
        ],
    )
    pieces = [Item.objects.create(id=20 + i, name=f"Pièce {i}", item_set=item_set) for i in range(2)]
    result = compute([SlotInput("head", pieces[0]), SlotInput("chest", pieces[1])])
    assert [b["threshold"] for b in result.active_set_bonuses] == [2]
    assert [b["threshold"] for b in result.inactive_set_bonuses] == [3]
    assert result.active_set_bonuses[0]["pieces"] == 2
