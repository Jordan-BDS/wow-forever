import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, fieldErrors, type Poll } from "@/api/client";
import { KEYS, useInvalidate, usePolls } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Button, Card, Field, Input, PageTitle, Select, Spinner } from "@/components/ui";
import { POLL_STATUS_LABEL, formatDateTime, formatRemaining, toLocalInput } from "@/lib/game";
import { isOfficerOrAbove } from "@/lib/roles";

export function PollsPage() {
  const me = useCurrentUser();
  const polls = usePolls();
  const [creating, setCreating] = useState(false);
  if (polls.isPending) return <Spinner />;

  const list = polls.data ?? [];
  const open = list.filter((p) => p.status === "proposals" || p.status === "votes");
  const done = list.filter((p) => p.status === "closed" || p.status === "validated");

  return (
    <>
      <PageTitle
        actions={
          isOfficerOrAbove(me.site_role) && (
            <Button variant={creating ? "ghost" : "primary"} onClick={() => setCreating((v) => !v)}>
              {creating ? "Annuler" : "Nouveau sondage"}
            </Button>
          )
        }
      >
        Sondages
      </PageTitle>
      {creating && <PollForm onDone={() => setCreating(false)} />}
      <section className="space-y-3">
        <h2 className="text-sm uppercase text-muted">En cours</h2>
        {open.length === 0 && <p className="text-sm text-muted">Aucun sondage en cours.</p>}
        {open.map((p) => (
          <PollCard key={p.id} poll={p} />
        ))}
      </section>
      {done.length > 0 && (
        <section className="mt-6 space-y-3">
          <h2 className="text-sm uppercase text-muted">Terminés</h2>
          {done.map((p) => (
            <PollCard key={p.id} poll={p} />
          ))}
        </section>
      )}
    </>
  );
}

export function PollCard({ poll }: { poll: Poll }) {
  const deadline = poll.status === "proposals" ? poll.proposals_end : poll.votes_end;
  const winner = poll.proposals.find((p) => p.id === poll.validated_proposal);
  return (
    <Link to={`/sondages/${poll.id}`} className="block text-text hover:text-text">
      <Card className="flex flex-wrap items-center justify-between gap-3 transition hover:border-gold/50">
        <div>
          <h3 className="font-display text-lg">{poll.title}</h3>
          <p className="text-xs text-muted">
            {POLL_STATUS_LABEL[poll.status]}
            {(poll.status === "proposals" || poll.status === "votes") && ` · ${formatRemaining(deadline)}`}
            {poll.status === "validated" && winner && ` · ${winner.text}`}
          </p>
        </div>
        <div className="text-right text-sm text-muted">
          <div>
            {poll.proposals.length} proposition{poll.proposals.length > 1 && "s"}
          </div>
          {poll.my_vote_count === 0 && poll.status !== "validated" && poll.status !== "closed" && (
            <div className="text-gold">Tu n'as pas encore voté</div>
          )}
        </div>
      </Card>
    </Link>
  );
}

function defaultPollForm() {
  const now = Date.now();
  const inDays = (d: number) => toLocalInput(new Date(now + d * 86_400_000));
  return {
    title: "Nom de la guilde",
    description: "",
    proposals_end: inDays(3),
    votes_end: inDays(6),
    max_proposals_per_user: 3,
    max_votes_per_user: "" as string | number,
    format_rule: "guild_name" as "free" | "guild_name",
    sets_guild_name: true,
  };
}

function PollForm({ onDone }: { onDone: () => void }) {
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const [form, setForm] = useState(defaultPollForm);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const create = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/polls/", {
        body: {
          title: form.title.trim(),
          description: form.description,
          proposals_end: new Date(form.proposals_end).toISOString(),
          votes_end: new Date(form.votes_end).toISOString(),
          max_proposals_per_user: Number(form.max_proposals_per_user),
          max_votes_per_user: form.max_votes_per_user === "" ? null : Number(form.max_votes_per_user),
          format_rule: form.format_rule,
          sets_guild_name: form.sets_guild_name,
        },
      });
      if (error || !data) throw error ?? new Error();
      return data;
    },
    onSuccess: async (poll) => {
      await invalidate(KEYS.polls);
      onDone();
      navigate(`/sondages/${poll.id}`);
    },
    onError: (e) => setErrors(fieldErrors(e)),
  });

  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <Card className="mb-6">
      <form
        className="grid gap-4 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          create.mutate();
        }}
      >
        <Field label="Titre">
          <Input value={form.title} required onChange={(e) => set({ title: e.target.value })} />
          {errors.title && <p className="text-xs text-danger">{errors.title}</p>}
        </Field>
        <Field label="Règle de format des propositions">
          <Select
            className="w-full"
            value={form.format_rule}
            onChange={(e) => set({ format_rule: e.target.value as "free" | "guild_name" })}
          >
            <option value="guild_name">Nom de guilde WoW (2–24 lettres et espaces)</option>
            <option value="free">Libre</option>
          </Select>
        </Field>
        <Field label="Fin des propositions">
          <Input
            type="datetime-local"
            value={form.proposals_end}
            required
            onChange={(e) => set({ proposals_end: e.target.value })}
          />
          {errors.proposals_end && <p className="text-xs text-danger">{errors.proposals_end}</p>}
        </Field>
        <Field label="Fin des votes">
          <Input
            type="datetime-local"
            value={form.votes_end}
            required
            onChange={(e) => set({ votes_end: e.target.value })}
          />
          {errors.votes_end && <p className="text-xs text-danger">{errors.votes_end}</p>}
        </Field>
        <Field label="Propositions max par personne">
          <Input
            type="number"
            min={1}
            value={form.max_proposals_per_user}
            onChange={(e) => set({ max_proposals_per_user: Number(e.target.value) })}
          />
        </Field>
        <Field label="Votes max par personne (vide = illimité)">
          <Input
            type="number"
            min={1}
            value={form.max_votes_per_user}
            onChange={(e) => set({ max_votes_per_user: e.target.value })}
          />
        </Field>
        <Field label="Description (consignes, contexte)">
          <textarea
            value={form.description}
            rows={3}
            onChange={(e) => set({ description: e.target.value })}
            className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm focus:border-gold focus:outline-none"
          />
        </Field>
        <div className="flex flex-col justify-end gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.sets_guild_name}
              onChange={(e) => set({ sets_guild_name: e.target.checked })}
              className="accent-gold"
            />
            Le résultat validé définit le nom de la guilde
          </label>
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={create.isPending}>
              Créer le sondage
            </Button>
            {errors.detail && <span className="text-sm text-danger">{errors.detail}</span>}
          </div>
        </div>
      </form>
      <p className="mt-3 text-xs text-muted">
        Heures de Paris. Les propositions ferment le{" "}
        {formatDateTime(new Date(form.proposals_end).toISOString())}, les votes le{" "}
        {formatDateTime(new Date(form.votes_end).toISOString())}.
      </p>
    </Card>
  );
}
