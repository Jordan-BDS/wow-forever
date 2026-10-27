import pytest

pytestmark = pytest.mark.django_db


def test_put_replaces_my_slots(as_user, member):
    client = as_user(member)
    slots = [
        {"weekday": 1, "start_hour": 20, "end_hour": 23},
        {"weekday": 6, "start_hour": 14, "end_hour": 18},
    ]
    response = client.put("/api/auth/me/availability/", slots, format="json")
    assert response.status_code == 200
    assert response.data == slots

    response = client.put("/api/auth/me/availability/", [slots[0]], format="json")
    assert response.data == [slots[0]]
    assert client.get("/api/auth/me/availability/").data == [slots[0]]


def test_rejects_invalid_ranges(as_user, member):
    client = as_user(member)
    bad = [
        [{"weekday": 1, "start_hour": 22, "end_hour": 22}],
        [{"weekday": 7, "start_hour": 1, "end_hour": 2}],
        [{"weekday": 1, "start_hour": 1, "end_hour": 25}],
    ]
    for slots in bad:
        assert client.put("/api/auth/me/availability/", slots, format="json").status_code == 400


def test_guild_view_aggregates_active_members_only(as_user, member, other_member):
    as_user(member).put(
        "/api/auth/me/availability/", [{"weekday": 2, "start_hour": 20, "end_hour": 24}], format="json"
    )
    as_user(other_member).put(
        "/api/auth/me/availability/", [{"weekday": 2, "start_hour": 21, "end_hour": 23}], format="json"
    )
    other_member.is_active = False
    other_member.save()
    response = as_user(member).get("/api/availability/")
    assert response.status_code == 200
    assert response.data == [
        {
            "user": member.pk,
            "display_name": member.display_name,
            "weekday": 2,
            "start_hour": 20,
            "end_hour": 24,
        }
    ]
