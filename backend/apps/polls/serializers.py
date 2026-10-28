from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.characters.serializers import OwnerSerializer

from .models import Poll, Proposal


class VoterSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    display_name = serializers.CharField()


class ProposalSerializer(serializers.ModelSerializer):
    author = OwnerSerializer(read_only=True)
    vote_count = serializers.IntegerField(read_only=True)
    voters = serializers.SerializerMethodField()
    has_voted = serializers.SerializerMethodField()

    class Meta:
        model = Proposal
        fields = ["id", "poll", "author", "text", "note", "vote_count", "voters", "has_voted", "created_at"]
        read_only_fields = ["poll", "created_at"]

    @extend_schema_field(VoterSerializer(many=True))
    def get_voters(self, proposal: Proposal) -> list[dict]:
        return [
            {"id": vote.user.pk, "display_name": vote.user.display_name}
            for vote in sorted(proposal.votes.all(), key=lambda v: v.created_at)
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_has_voted(self, proposal: Proposal) -> bool:
        user = self.context["request"].user
        return any(vote.user_id == user.pk for vote in proposal.votes.all())


class ProposalCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proposal
        fields = ["text", "note"]
        extra_kwargs = {"text": {"min_length": 1}}


class PollSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(
        choices=["proposals", "votes", "closed", "validated", "cancelled"], read_only=True
    )
    created_by = OwnerSerializer(read_only=True)
    validated_by = OwnerSerializer(read_only=True)
    proposals = serializers.SerializerMethodField()
    my_proposal_count = serializers.SerializerMethodField()
    my_vote_count = serializers.SerializerMethodField()

    class Meta:
        model = Poll
        fields = [
            "id",
            "title",
            "description",
            "proposals_end",
            "votes_end",
            "max_proposals_per_user",
            "max_votes_per_user",
            "format_rule",
            "sets_guild_name",
            "status",
            "validated_proposal",
            "validation_note",
            "validated_at",
            "cancelled_at",
            "validated_by",
            "created_by",
            "created_at",
            "proposals",
            "my_proposal_count",
            "my_vote_count",
        ]
        read_only_fields = [
            "validated_proposal",
            "validation_note",
            "validated_at",
            "cancelled_at",
            "created_at",
        ]
        extra_kwargs = {"max_proposals_per_user": {"min_value": 1}, "max_votes_per_user": {"min_value": 1}}

    def validate(self, attrs):
        proposals_end = attrs.get("proposals_end", self.instance.proposals_end if self.instance else None)
        votes_end = attrs.get("votes_end", self.instance.votes_end if self.instance else None)
        if proposals_end and votes_end and votes_end <= proposals_end:
            raise serializers.ValidationError(
                {"votes_end": "La fin des votes doit suivre la fin des propositions."}
            )
        return attrs

    @staticmethod
    def _ranked(poll: Poll):
        return poll.ranked_proposals().select_related("author").prefetch_related("votes__user")

    @extend_schema_field(ProposalSerializer(many=True))
    def get_proposals(self, poll: Poll) -> list[dict]:
        return ProposalSerializer(self._ranked(poll), many=True, context=self.context).data

    @extend_schema_field(serializers.IntegerField())
    def get_my_proposal_count(self, poll: Poll) -> int:
        return poll.proposals.filter(author=self.context["request"].user).count()

    @extend_schema_field(serializers.IntegerField())
    def get_my_vote_count(self, poll: Poll) -> int:
        return poll.proposals.filter(votes__user=self.context["request"].user).count()


class ValidateSerializer(serializers.Serializer):
    proposal = serializers.PrimaryKeyRelatedField(queryset=Proposal.objects.all())
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)
