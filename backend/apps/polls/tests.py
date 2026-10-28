from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.guild.models import GuildSettings
from apps.polls.models import Poll, Proposal, Vote

pytestmark = pytest.mark.django_db

NOW = timezone.now()


def make_poll(creator, *, proposals_in=timedelta(days=2), votes_in=timedelta(days=5), **overrides) -> Poll:
    data = {
        "title": "Nom de la guilde",
        "proposals_end": NOW + proposals_in,
        "votes_end": NOW + votes_in,
        "format_rule": "guild_name",
        "sets_guild_name": True,
        "created_by": creator,
    }
    return Poll.objects.create(**{**data, **overrides})


def propose(client, poll, text, note=""):
    return client.post(f"/api/polls/{poll.pk}/propose/", {"text": text, "note": note}, format="json")


class TestPollManagement:
    def test_officer_creates_poll(self, as_user, officer):
        response = as_user(officer).post(
            "/api/polls/",
            {
                "title": "Nom de la guilde",
                "proposals_end": (NOW + timedelta(days=2)).isoformat(),
                "votes_end": (NOW + timedelta(days=5)).isoformat(),
                "format_rule": "guild_name",
                "sets_guild_name": True,
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["status"] == "proposals"
        assert response.data["max_proposals_per_user"] == 3
        assert response.data["max_votes_per_user"] is None
        assert response.data["created_by"]["id"] == officer.pk

    def test_member_cannot_create_poll(self, as_user, member):
        response = as_user(member).post(
            "/api/polls/",
            {"title": "x", "proposals_end": NOW.isoformat(), "votes_end": NOW.isoformat()},
            format="json",
        )
        assert response.status_code == 403

    def test_votes_end_must_follow_proposals_end(self, as_user, officer):
        response = as_user(officer).post(
            "/api/polls/",
            {
                "title": "x",
                "proposals_end": (NOW + timedelta(days=5)).isoformat(),
                "votes_end": (NOW + timedelta(days=2)).isoformat(),
            },
            format="json",
        )
        assert response.status_code == 400
        assert "votes_end" in response.data

    def test_cannot_delete_poll_with_proposals(self, as_user, officer, member):
        poll = make_poll(officer)
        assert as_user(officer).delete(f"/api/polls/{poll.pk}/").status_code == 204
        poll = make_poll(officer)
        propose(as_user(member), poll, "Les Potes")
        assert as_user(officer).delete(f"/api/polls/{poll.pk}/").status_code == 403

    def test_officer_cancels_poll_which_freezes_it(self, as_user, officer, member, gm):
        from apps.notifications.models import Notification

        poll = make_poll(officer)
        propose(as_user(member), poll, "Les Potes")
        assert as_user(member).post(f"/api/polls/{poll.pk}/cancel/").status_code == 403
        response = as_user(officer).post(f"/api/polls/{poll.pk}/cancel/")
        assert response.status_code == 200 and response.data["status"] == "cancelled"
        assert len(response.data["proposals"]) == 1  # propositions conservées
        assert Notification.objects.filter(kind="poll_cancelled").count() == 1
        assert as_user(officer).post(f"/api/polls/{poll.pk}/cancel/").status_code == 200  # idempotent
        assert Notification.objects.filter(kind="poll_cancelled").count() == 1
        # Plus rien ne bouge : ni proposition, ni vote, ni modification, ni validation.
        assert propose(as_user(member), poll, "Autre").status_code == 400
        proposal_id = response.data["proposals"][0]["id"]
        assert as_user(member).post(f"/api/proposals/{proposal_id}/vote/").status_code == 400
        assert (
            as_user(officer).patch(f"/api/polls/{poll.pk}/", {"title": "x"}, format="json").status_code == 403
        )
        assert as_user(gm).post(f"/api/polls/{poll.pk}/validate/", {}, format="json").status_code in (
            400,
            403,
        )
        # Un sondage validé ne peut pas être annulé.
        done = make_poll(officer)
        winner = propose(as_user(member), done, "Gagnant").data["id"]
        Poll.objects.filter(pk=done.pk).update(
            proposals_end=NOW - timedelta(days=2), votes_end=NOW - timedelta(hours=1)
        )
        assert (
            as_user(gm)
            .post(f"/api/polls/{done.pk}/validate/", {"proposal": winner}, format="json")
            .status_code
            == 200
        )
        assert as_user(officer).post(f"/api/polls/{done.pk}/cancel/").status_code == 403


class TestProposals:
    def test_member_proposes_up_to_the_limit(self, as_user, officer, member):
        poll = make_poll(officer)
        client = as_user(member)
        for name in ("Les Potes", "Forever Young", "Azeroth Club"):
            assert propose(client, poll, name).status_code == 201
        response = propose(client, poll, "Un de trop")
        assert response.status_code == 400
        poll_data = client.get(f"/api/polls/{poll.pk}/").data
        assert poll_data["my_proposal_count"] == 3

    def test_duplicates_are_rejected_case_and_space_insensitive(self, as_user, officer, member, other_member):
        poll = make_poll(officer)
        assert propose(as_user(member), poll, "Les  Potes").status_code == 201
        response = propose(as_user(other_member), poll, "les potes")
        assert response.status_code == 400
        assert "text" in response.data

    def test_guild_name_format_rule(self, as_user, officer, member):
        poll = make_poll(officer)
        client = as_user(member)
        assert propose(client, poll, "Potes 2026").status_code == 400
        assert propose(client, poll, "L'Ordre").status_code == 400
        assert propose(client, poll, "A").status_code == 400
        assert propose(client, poll, "Nom beaucoup trop long pour WoW").status_code == 400
        assert propose(client, poll, "Éclaireurs de Lordaeron").status_code == 201

    def test_free_format_accepts_anything(self, as_user, officer, member):
        poll = make_poll(officer, format_rule="free", sets_guild_name=False)
        assert propose(as_user(member), poll, "Mardi 21h !").status_code == 201

    def test_no_proposals_after_phase(self, as_user, officer, member):
        poll = make_poll(officer, proposals_in=-timedelta(hours=1))
        assert propose(as_user(member), poll, "Trop tard").status_code == 400

    def test_author_withdraws_during_phase_only(self, as_user, officer, member):
        poll = make_poll(officer)
        proposal_id = propose(as_user(member), poll, "Les Potes").data["id"]
        assert as_user(member).delete(f"/api/proposals/{proposal_id}/").status_code == 204
        poll.proposals_end = NOW - timedelta(hours=1)
        poll.save()
        proposal = Proposal.objects.create(poll=poll, author=member, text="Tardif")
        assert as_user(member).delete(f"/api/proposals/{proposal.pk}/").status_code == 403

    def test_officer_removes_any_proposal(self, as_user, officer, member, other_member):
        poll = make_poll(officer)
        proposal_id = propose(as_user(member), poll, "Vulgaire").data["id"]
        assert as_user(other_member).delete(f"/api/proposals/{proposal_id}/").status_code == 403
        assert as_user(officer).delete(f"/api/proposals/{proposal_id}/").status_code == 204


class TestVotes:
    def test_vote_is_idempotent_and_public(self, as_user, officer, member, other_member):
        poll = make_poll(officer)
        proposal_id = propose(as_user(member), poll, "Les Potes").data["id"]
        client = as_user(other_member)
        first = client.post(f"/api/proposals/{proposal_id}/vote/")
        again = client.post(f"/api/proposals/{proposal_id}/vote/")
        assert first.status_code == again.status_code == 200
        assert again.data["vote_count"] == 1
        assert again.data["has_voted"] is True
        assert again.data["voters"] == [{"id": other_member.pk, "display_name": other_member.display_name}]

    def test_unlimited_votes_by_default_and_own_proposal_allowed(self, as_user, officer, member):
        poll = make_poll(officer)
        client = as_user(member)
        ids = [propose(client, poll, name).data["id"] for name in ("Un", "Deux", "Trois")]
        for pid in ids:
            assert client.post(f"/api/proposals/{pid}/vote/").status_code == 200
        assert client.get(f"/api/polls/{poll.pk}/").data["my_vote_count"] == 3

    def test_vote_limit_when_configured(self, as_user, officer, member):
        poll = make_poll(officer, max_votes_per_user=1)
        client = as_user(member)
        a, b = (propose(client, poll, name).data["id"] for name in ("Un", "Deux"))
        assert client.post(f"/api/proposals/{a}/vote/").status_code == 200
        assert client.post(f"/api/proposals/{b}/vote/").status_code == 400
        assert client.post(f"/api/proposals/{a}/unvote/").status_code == 200
        assert client.post(f"/api/proposals/{b}/vote/").status_code == 200

    def test_voting_continues_after_proposals_close_and_stops_at_votes_end(self, as_user, officer, member):
        poll = make_poll(officer)
        proposal_id = propose(as_user(member), poll, "Les Potes").data["id"]
        poll.proposals_end = NOW - timedelta(hours=1)
        poll.save()
        assert as_user(member).post(f"/api/proposals/{proposal_id}/vote/").status_code == 200
        poll.votes_end = NOW - timedelta(minutes=1)
        poll.save()
        assert as_user(member).post(f"/api/proposals/{proposal_id}/unvote/").status_code == 400

    def test_ranking_by_votes_then_seniority(self, as_user, officer, member, other_member):
        poll = make_poll(officer)
        first = propose(as_user(member), poll, "Premier").data["id"]
        second = propose(as_user(member), poll, "Second").data["id"]
        third = propose(as_user(member), poll, "Troisième").data["id"]
        for user in (member, other_member):
            Vote.objects.create(proposal_id=third, user=user)
        Vote.objects.create(proposal_id=second, user=member)
        data = as_user(member).get(f"/api/polls/{poll.pk}/").data
        assert [p["id"] for p in data["proposals"]] == [third, second, first]


class TestValidation:
    def closed_poll_with_votes(self, officer, member, other_member):
        poll = make_poll(officer, proposals_in=-timedelta(days=2), votes_in=-timedelta(hours=1))
        top = Proposal.objects.create(poll=poll, author=member, text="Les Potes")
        runner_up = Proposal.objects.create(poll=poll, author=other_member, text="Forever Young")
        Vote.objects.create(proposal=top, user=member)
        Vote.objects.create(proposal=top, user=other_member)
        Vote.objects.create(proposal=runner_up, user=member)
        return poll, top, runner_up

    def test_gm_validates_winner_and_guild_name_is_set(self, as_user, gm, officer, member, other_member):
        poll, top, _ = self.closed_poll_with_votes(officer, member, other_member)
        response = as_user(gm).post(f"/api/polls/{poll.pk}/validate/", {"proposal": top.pk}, format="json")
        assert response.status_code == 200, response.data
        assert response.data["status"] == "validated"
        assert response.data["validated_proposal"] == top.pk
        assert response.data["validated_by"]["id"] == gm.pk
        assert GuildSettings.load().name == "Les Potes"

    def test_picking_runner_up_requires_a_note(self, as_user, gm, officer, member, other_member):
        poll, _, runner_up = self.closed_poll_with_votes(officer, member, other_member)
        client = as_user(gm)
        denied = client.post(f"/api/polls/{poll.pk}/validate/", {"proposal": runner_up.pk}, format="json")
        assert denied.status_code == 400
        assert "note" in denied.data
        ok = client.post(
            f"/api/polls/{poll.pk}/validate/",
            {"proposal": runner_up.pk, "note": "Nom déjà pris sur le royaume"},
            format="json",
        )
        assert ok.status_code == 200
        assert GuildSettings.load().name == "Forever Young"

    def test_only_gm_validates_and_only_when_closed(self, as_user, gm, officer, member, other_member):
        poll, top, _ = self.closed_poll_with_votes(officer, member, other_member)
        assert (
            as_user(officer).post(f"/api/polls/{poll.pk}/validate/", {"proposal": top.pk}).status_code == 403
        )
        poll.votes_end = NOW + timedelta(days=1)
        poll.save()
        assert as_user(gm).post(f"/api/polls/{poll.pk}/validate/", {"proposal": top.pk}).status_code == 400

    def test_validated_poll_is_frozen(self, as_user, gm, officer, member, other_member):
        poll, top, _ = self.closed_poll_with_votes(officer, member, other_member)
        as_user(gm).post(f"/api/polls/{poll.pk}/validate/", {"proposal": top.pk}, format="json")
        assert (
            as_user(officer).patch(f"/api/polls/{poll.pk}/", {"title": "x"}, format="json").status_code == 403
        )
        assert as_user(officer).delete(f"/api/proposals/{top.pk}/").status_code == 403

    def test_proposal_from_another_poll_is_rejected(self, as_user, gm, officer, member, other_member):
        poll, _, _ = self.closed_poll_with_votes(officer, member, other_member)
        other = make_poll(officer)
        foreign = Proposal.objects.create(poll=other, author=member, text="Ailleurs")
        response = as_user(gm).post(
            f"/api/polls/{poll.pk}/validate/", {"proposal": foreign.pk}, format="json"
        )
        assert response.status_code == 400


def test_poll_status_timeline(officer):
    assert make_poll(officer).status == "proposals"
    assert make_poll(officer, proposals_in=-timedelta(hours=1)).status == "votes"
    assert (
        make_poll(officer, proposals_in=-timedelta(days=2), votes_in=-timedelta(hours=1)).status == "closed"
    )


def test_user_fixture_display_names_are_distinct(member, other_member):
    assert User.objects.count() == 2
    assert member.display_name != other_member.display_name


def test_poll_lifecycle_enqueues_channel_notifications(as_user, officer, gm, member, other_member):
    from apps.notifications.models import Notification

    response = as_user(officer).post(
        "/api/polls/",
        {
            "title": "Nom",
            "proposals_end": (NOW + timedelta(days=1)).isoformat(),
            "votes_end": (NOW + timedelta(days=2)).isoformat(),
            "sets_guild_name": True,
        },
        format="json",
    )
    # L'annonce, c'est le message de suivi synchronisé dans le salon des sondages.
    assert Notification.objects.get().kind == "poll_sync"
    poll = Poll.objects.get(pk=response.data["id"])
    proposal = Proposal.objects.create(poll=poll, author=member, text="Les Potes")
    poll.proposals_end, poll.votes_end = NOW - timedelta(days=2), NOW - timedelta(hours=1)
    poll.save()
    as_user(gm).post(f"/api/polls/{poll.pk}/validate/", {"proposal": proposal.pk}, format="json")
    validated = Notification.objects.get(kind="poll_validated")
    assert "Les Potes" in validated.text and "nouveau nom" in validated.text
    assert (
        Notification.objects.filter(kind="poll_sync").count() == 1
    )  # dédupliquée tant qu'elle est en attente


class TestDiscordPollSync:
    def test_every_change_requests_a_refresh_once(self, as_user, officer, member, other_member):
        from apps.notifications.models import Notification

        def pending():
            return Notification.objects.filter(kind="poll_sync", status="pending").count()

        def acknowledge():
            Notification.objects.update(status="sent")

        poll = make_poll(officer)
        acknowledge()
        proposal_id = propose(as_user(member), poll, "Les Potes").data["id"]
        assert pending() == 1
        propose(as_user(other_member), poll, "Les Zouaves")
        assert pending() == 1  # toujours une seule demande en attente
        acknowledge()
        assert as_user(other_member).post(f"/api/proposals/{proposal_id}/vote/").status_code == 200
        assert pending() == 1
        acknowledge()
        as_user(other_member).post(f"/api/proposals/{proposal_id}/vote/")  # déjà voté : rien ne change
        assert pending() == 0
        as_user(other_member).post(f"/api/proposals/{proposal_id}/unvote/")
        assert pending() == 1
        acknowledge()
        as_user(other_member).post(f"/api/proposals/{proposal_id}/unvote/")  # déjà retiré
        assert pending() == 0
        as_user(officer).patch(
            f"/api/polls/{poll.pk}/", {"votes_end": (NOW + timedelta(days=9)).isoformat()}, format="json"
        )
        assert pending() == 1
        acknowledge()
        assert as_user(member).delete(f"/api/proposals/{proposal_id}/").status_code == 204
        assert pending() == 1
        acknowledge()
        as_user(officer).post(f"/api/polls/{poll.pk}/cancel/")
        assert pending() == 1

    def test_message_text_follows_the_phases(self, as_user, officer, member, other_member, gm):
        from apps.notifications import services

        poll = make_poll(officer, sets_guild_name=True, max_votes_per_user=2)
        text = services.poll_message_text(poll)
        assert "propositions ouvertes" in text and "Aucune proposition" in text
        assert "2 vote(s)" in text and "nom de la guilde" in text and f"/sondages/{poll.pk}" in text
        first = propose(as_user(member), poll, "Les Potes").data["id"]
        propose(as_user(other_member), poll, "Les Zouaves")
        as_user(other_member).post(f"/api/proposals/{first}/vote/")
        poll.refresh_from_db()
        text = services.poll_message_text(poll)
        assert text.index("1. **Les Potes** — 1 vote(s) · User 101") < text.index(
            "2. **Les Zouaves** — 0 vote(s)"
        )
        Poll.objects.filter(pk=poll.pk).update(proposals_end=NOW - timedelta(hours=1))
        poll.refresh_from_db()
        assert "vote en cours" in services.poll_message_text(poll)
        Poll.objects.filter(pk=poll.pk).update(votes_end=NOW - timedelta(minutes=1))
        poll.refresh_from_db()
        assert "votes clos" in services.poll_message_text(poll)
        as_user(gm).post(f"/api/polls/{poll.pk}/validate/", {"proposal": first}, format="json")
        poll.refresh_from_db()
        text = services.poll_message_text(poll)
        assert text.startswith("🏆") and "🏆 **Les Potes**" in text
        poll.cancelled_at = NOW
        assert services.poll_message_text(poll).startswith("❌")

    def test_phase_change_without_action_refreshes_the_message(self, officer):
        from apps.notifications.models import Notification
        from apps.notifications.reminders import scan_due_reminders

        poll = make_poll(officer, proposals_in=timedelta(days=3), votes_in=timedelta(days=6))
        Notification.objects.all().delete()
        Poll.objects.filter(pk=poll.pk).update(discord_message_id="42", discord_synced_status="proposals")
        assert scan_due_reminders(NOW) == 0  # toujours en phase de propositions : rien à faire
        Poll.objects.filter(pk=poll.pk).update(proposals_end=NOW - timedelta(hours=1))
        assert scan_due_reminders(NOW) == 1
        assert Notification.objects.get(kind="poll_sync").poll_id == poll.pk
        # Un sondage jamais publié sur Discord (pas de message) n'est pas concerné.
        other = make_poll(officer, proposals_in=timedelta(days=-1), votes_in=timedelta(days=6))
        Notification.objects.all().delete()
        assert scan_due_reminders(NOW) == 0 or Notification.objects.filter(poll=other).count() == 0

    def test_discord_url_when_mirrored(self, as_user, officer, settings):
        from apps.guild.models import GuildSettings

        settings.DISCORD_GUILD_ID = "4242"
        poll = make_poll(officer)
        assert as_user(officer).get(f"/api/polls/{poll.pk}/").data["discord_url"] is None
        Poll.objects.filter(pk=poll.pk).update(discord_message_id="77")
        stored = GuildSettings.load()
        stored.discord_polls_channel_id = "55"
        stored.save()
        url = as_user(officer).get(f"/api/polls/{poll.pk}/").data["discord_url"]
        assert url == "https://discord.com/channels/4242/55/77"
