import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { Navigate, useParams } from "react-router";
import { api, errorMessage, type Poll, type Proposal } from "@/api/client";
import { GUILD_KEY } from "@/api/guild";
import { KEYS, useInvalidate, usePoll } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Button, Card, Field, Input, PageTitle, Spinner } from "@/components/ui";
import { POLL_STATUS_LABEL, formatDateTime, formatRemaining } from "@/lib/game";
import { isOfficerOrAbove } from "@/lib/roles";

export function PollPage() {
  const id = Number(useParams().id);
  const poll = usePoll(id);
  if (poll.isPending) return <Spinner />;
  if (poll.isError || !poll.data) return <Navigate to="/sondages" replace />;
  return <PollDetail poll={poll.data} />;
}

function PollDetail({ poll }: { poll: Poll }) {
  const me = useCurrentUser();
  const invalidate = useInvalidate();
  const [error, setError] = useState<string | null>(null);
  const refresh = () => invalidate(KEYS.poll(poll.id), KEYS.polls);

  const vote = useMutation({
    mutationFn: async ({ proposal, on }: { proposal: Proposal; on: boolean }) => {
      const path = on ? "/api/proposals/{id}/vote/" : "/api/proposals/{id}/unvote/";
      const { error } = await api.POST(path, { params: { path: { id: proposal.id } } });
      if (error) throw error;
    },
    onSuccess: refresh,
    onError: (e) => setError(errorMessage(e)),
  });

  const withdraw = useMutation({
    mutationFn: async (proposal: Proposal) => {
      const { error } = await api.DELETE("/api/proposals/{id}/", { params: { path: { id: proposal.id } } });
      if (error) throw error;
    },
    onSuccess: refresh,
    onError: (e) => setError(errorMessage(e)),
  });

  const isOfficer = isOfficerOrAbove(me.site_role);
  const canPropose =
    poll.status === "proposals" && poll.my_proposal_count < (poll.max_proposals_per_user ?? 3);
  const canVote = poll.status === "proposals" || poll.status === "votes";
  const voteLimitReached = poll.max_votes_per_user != null && poll.my_vote_count >= poll.max_votes_per_user;
  const winner = poll.proposals.find((p) => p.id === poll.validated_proposal);
  const topVotes = poll.proposals[0]?.vote_count ?? 0;

  return (
    <>
      <PageTitle>{poll.title}</PageTitle>
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          {poll.status === "validated" && winner && (
            <Card className="border-gold/60 bg-gold/10">
              <p className="text-xs uppercase text-gold">Résultat validé</p>
              <p className="font-display text-2xl">{winner.text}</p>
              <p className="mt-1 text-xs text-muted">
                Validé par {poll.validated_by?.display_name} le {formatDateTime(poll.validated_at!)}
                {poll.validation_note && ` · ${poll.validation_note}`}
              </p>
            </Card>
          )}
          {error && <p className="text-sm text-danger">{error}</p>}
          {canPropose && <ProposeForm poll={poll} onDone={refresh} />}
          {poll.status === "proposals" && !canPropose && (
            <p className="text-sm text-muted">
              Tu as fait tes {poll.max_proposals_per_user} propositions. Retire-en une pour en proposer une
              autre.
            </p>
          )}
          <Card className="p-0">
            {poll.proposals.length === 0 ? (
              <p className="p-6 text-center text-sm text-muted">Pas encore de proposition. Lance-toi !</p>
            ) : (
              <ol className="divide-y divide-border/60">
                {poll.proposals.map((proposal, index) => {
                  const mine = proposal.author.id === me.id;
                  const isTop = proposal.vote_count === topVotes && topVotes > 0;
                  return (
                    <li key={proposal.id} className="flex flex-wrap items-center gap-3 p-3">
                      <span className="w-6 text-right font-mono text-sm text-muted">{index + 1}.</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={clsx("font-medium", isTop && "text-gold")}>{proposal.text}</span>
                          {proposal.id === poll.validated_proposal && (
                            <span className="rounded border border-gold/50 px-1.5 text-xs text-gold">
                              gagnant
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted">
                          par {proposal.author.display_name}
                          {proposal.note && ` · ${proposal.note}`}
                        </p>
                        {proposal.voters.length > 0 && (
                          <p className="mt-1 text-xs text-muted">
                            {proposal.voters.map((v) => v.display_name).join(", ")}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="min-w-8 text-center text-lg font-semibold">
                          {proposal.vote_count}
                        </span>
                        {canVote && (
                          <Button
                            variant={proposal.has_voted ? "primary" : "ghost"}
                            disabled={vote.isPending || (!proposal.has_voted && voteLimitReached)}
                            onClick={() => vote.mutate({ proposal, on: !proposal.has_voted })}
                            aria-pressed={proposal.has_voted}
                          >
                            {proposal.has_voted ? "Voté ✓" : "Voter"}
                          </Button>
                        )}
                        {((mine && poll.status === "proposals") ||
                          (isOfficer && poll.status !== "validated")) && (
                          <Button
                            variant="danger"
                            disabled={withdraw.isPending}
                            aria-label="Retirer la proposition"
                            onClick={() => {
                              if (window.confirm(`Retirer « ${proposal.text} » ?`)) withdraw.mutate(proposal);
                            }}
                          >
                            ✕
                          </Button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="space-y-2 text-sm">
            <p className="font-medium">{POLL_STATUS_LABEL[poll.status]}</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              <dt className="text-muted">Propositions</dt>
              <dd>
                {formatDateTime(poll.proposals_end)}
                <span className="text-muted"> · {formatRemaining(poll.proposals_end)}</span>
              </dd>
              <dt className="text-muted">Votes</dt>
              <dd>
                {formatDateTime(poll.votes_end)}
                <span className="text-muted"> · {formatRemaining(poll.votes_end)}</span>
              </dd>
              <dt className="text-muted">Règles</dt>
              <dd>
                {poll.max_proposals_per_user ?? 3} proposition{(poll.max_proposals_per_user ?? 3) > 1 && "s"}{" "}
                par personne,{" "}
                {poll.max_votes_per_user == null ? "votes illimités" : `${poll.max_votes_per_user} vote(s)`}
                {poll.format_rule === "guild_name" && ", format nom de guilde"}
              </dd>
              {poll.sets_guild_name && (
                <>
                  <dt className="text-muted">Effet</dt>
                  <dd>Le gagnant devient le nom de la guilde</dd>
                </>
              )}
            </dl>
            {poll.description && (
              <p className="whitespace-pre-wrap border-t border-border pt-2">{poll.description}</p>
            )}
            <p className="text-xs text-muted">Créé par {poll.created_by?.display_name}</p>
          </Card>
          {poll.status === "closed" && me.site_role === "gm" && <ValidateForm poll={poll} />}
          {poll.status === "closed" && me.site_role !== "gm" && (
            <Card className="text-sm text-muted">Les votes sont clos. Le GM valide le résultat.</Card>
          )}
        </div>
      </div>
    </>
  );
}

function ProposeForm({ poll, onDone }: { poll: Poll; onDone: () => Promise<unknown> }) {
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const propose = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/polls/{id}/propose/", {
        params: { path: { id: poll.id } },
        body: { text: text.trim(), note: note.trim() },
      });
      if (error) throw error;
    },
    onSuccess: async () => {
      setText("");
      setNote("");
      setError(null);
      await onDone();
    },
    onError: (e) => setError(errorMessage(e)),
  });

  return (
    <Card>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          propose.mutate();
        }}
      >
        <Field label={`Ta proposition (${poll.my_proposal_count}/${poll.max_proposals_per_user})`}>
          <Input
            value={text}
            required
            maxLength={poll.format_rule === "guild_name" ? 24 : 120}
            placeholder={poll.format_rule === "guild_name" ? "Ex. Les Potes" : ""}
            onChange={(e) => setText(e.target.value)}
            className="min-w-56"
          />
        </Field>
        <Field label="Note (facultative)">
          <Input
            value={note}
            maxLength={240}
            onChange={(e) => setNote(e.target.value)}
            className="min-w-56"
          />
        </Field>
        <Button type="submit" disabled={propose.isPending || !text.trim()}>
          Proposer
        </Button>
      </form>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
    </Card>
  );
}

function ValidateForm({ poll }: { poll: Poll }) {
  const invalidate = useInvalidate();
  const [proposalId, setProposalId] = useState<number>(poll.proposals[0]?.id ?? 0);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const isTop = proposalId === poll.proposals[0]?.id;

  const validate = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/polls/{id}/validate/", {
        params: { path: { id: poll.id } },
        body: { proposal: proposalId, note },
      });
      if (error) throw error;
    },
    onSuccess: () => invalidate(KEYS.poll(poll.id), KEYS.polls, GUILD_KEY),
    onError: (e) => setError(errorMessage(e)),
  });

  if (poll.proposals.length === 0) {
    return <Card className="text-sm text-muted">Aucune proposition à valider.</Card>;
  }

  return (
    <Card className="space-y-3">
      <h2 className="font-display text-lg">Valider le résultat</h2>
      <Field label="Proposition retenue">
        <select
          value={proposalId}
          onChange={(e) => setProposalId(Number(e.target.value))}
          className="w-full rounded-md border border-border bg-bg px-2 py-1.5 text-sm"
        >
          {poll.proposals.map((p) => (
            <option key={p.id} value={p.id}>
              {p.text} ({p.vote_count})
            </option>
          ))}
        </select>
      </Field>
      <Field label={isTop ? "Justification (facultative)" : "Justification (obligatoire)"}>
        <Input value={note} required={!isTop} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {poll.sets_guild_name && (
        <p className="text-xs text-muted">Le nom de la guilde sera mis à jour avec la proposition retenue.</p>
      )}
      <Button disabled={validate.isPending} onClick={() => validate.mutate()}>
        Valider
      </Button>
      {error && <p className="text-sm text-danger">{error}</p>}
    </Card>
  );
}
