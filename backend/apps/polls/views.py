from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsGM, IsOfficerOrAbove
from apps.guild.models import GuildSettings
from apps.notifications import services as notify

from .models import Poll, PollStatus, Proposal, Vote, normalize
from .serializers import PollSerializer, ProposalCreateSerializer, ProposalSerializer, ValidateSerializer


class PollViewSet(viewsets.ModelViewSet):
    """Sondages à propositions : lecture pour tous, réglages par les officiers, validation par le GM."""

    serializer_class = PollSerializer
    queryset = Poll.objects.select_related("created_by", "validated_by")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [permissions.IsAuthenticated(), IsOfficerOrAbove()]
        if self.action == "validate":
            return [permissions.IsAuthenticated(), IsGM()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        poll = serializer.save(created_by=self.request.user)
        notify.poll_opened(poll)

    def perform_update(self, serializer):
        if serializer.instance.status == PollStatus.VALIDATED:
            raise PermissionDenied("Un sondage validé ne se modifie plus.")
        serializer.save()

    def perform_destroy(self, instance: Poll):
        if instance.proposals.exists():
            raise PermissionDenied("Un sondage ne peut être supprimé qu'avant sa première proposition.")
        instance.delete()

    @extend_schema(request=ProposalCreateSerializer, responses={201: ProposalSerializer})
    @action(detail=True, methods=["post"])
    def propose(self, request: Request, pk=None) -> Response:
        poll: Poll = self.get_object()
        if not poll.accepts_proposals:
            raise ValidationError({"detail": "Les propositions sont closes."})
        serializer = ProposalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = " ".join(serializer.validated_data["text"].split())
        if error := poll.validate_text(text):
            raise ValidationError({"text": error})
        if poll.proposals.filter(author=request.user).count() >= poll.max_proposals_per_user:
            raise ValidationError(
                {"detail": f"Tu as déjà fait {poll.max_proposals_per_user} propositions, retire-en une."}
            )
        if poll.proposals.filter(normalized_text=normalize(text)).exists():
            raise ValidationError({"text": "Cette proposition existe déjà."})
        proposal = Proposal.objects.create(
            poll=poll, author=request.user, text=text, note=serializer.validated_data.get("note", "")
        )
        proposal = (
            poll.ranked_proposals()
            .select_related("author")
            .prefetch_related("votes__user")
            .get(pk=proposal.pk)
        )
        return Response(
            ProposalSerializer(proposal, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=ValidateSerializer, responses=PollSerializer)
    @action(detail=True, methods=["post"])
    def validate(self, request: Request, pk=None) -> Response:
        poll: Poll = self.get_object()
        if poll.status != PollStatus.CLOSED:
            raise ValidationError({"detail": "Le sondage doit être clos pour être validé."})
        serializer = ValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        proposal: Proposal = serializer.validated_data["proposal"]
        note = serializer.validated_data.get("note", "").strip()
        if proposal.poll_id != poll.pk:
            raise ValidationError({"proposal": "Cette proposition n'appartient pas à ce sondage."})
        winner = poll.ranked_proposals().first()
        if winner and winner.pk != proposal.pk and not note:
            raise ValidationError(
                {"note": "Justification obligatoire si tu ne retiens pas la proposition la plus votée."}
            )
        with transaction.atomic():
            poll.validated_proposal = proposal
            poll.validation_note = note
            poll.validated_at = timezone.now()
            poll.validated_by = request.user
            poll.save()
            if poll.sets_guild_name:
                settings = GuildSettings.load()
                settings.name = proposal.text[:24]
                settings.save()
            notify.poll_validated(poll)
        return Response(self.get_serializer(poll).data)


class ProposalViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Retrait d'une proposition et votes."""

    serializer_class = ProposalSerializer
    queryset = Proposal.objects.select_related("poll", "author").prefetch_related("votes__user")

    def perform_destroy(self, instance: Proposal):
        user = self.request.user
        poll = instance.poll
        if poll.status == PollStatus.VALIDATED:
            raise PermissionDenied("Le sondage est validé.")
        if instance.author_id == user.pk:
            if not poll.accepts_proposals:
                raise PermissionDenied("On ne retire plus de proposition après la phase de propositions.")
        elif not user.is_officer_or_above:
            raise PermissionDenied("Tu ne peux retirer que tes propres propositions.")
        instance.delete()

    def _refreshed(self, proposal: Proposal) -> Response:
        proposal = (
            proposal.poll.ranked_proposals()
            .select_related("author")
            .prefetch_related("votes__user")
            .get(pk=proposal.pk)
        )
        return Response(self.get_serializer(proposal).data)

    @extend_schema(request=None, responses=ProposalSerializer)
    @action(detail=True, methods=["post"])
    def vote(self, request: Request, pk=None) -> Response:
        proposal: Proposal = self.get_object()
        poll = proposal.poll
        if not poll.accepts_votes:
            raise ValidationError({"detail": "Les votes sont clos."})
        if Vote.objects.filter(proposal=proposal, user=request.user).exists():
            return self._refreshed(proposal)
        if poll.max_votes_per_user is not None:
            count = Vote.objects.filter(proposal__poll=poll, user=request.user).count()
            if count >= poll.max_votes_per_user:
                raise ValidationError({"detail": f"Tu as déjà utilisé tes {poll.max_votes_per_user} votes."})
        Vote.objects.create(proposal=proposal, user=request.user)
        return self._refreshed(proposal)

    @extend_schema(request=None, responses=ProposalSerializer)
    @action(detail=True, methods=["post"])
    def unvote(self, request: Request, pk=None) -> Response:
        proposal: Proposal = self.get_object()
        if not proposal.poll.accepts_votes:
            raise ValidationError({"detail": "Les votes sont clos."})
        Vote.objects.filter(proposal=proposal, user=request.user).delete()
        return self._refreshed(proposal)
