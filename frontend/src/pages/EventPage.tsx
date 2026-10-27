import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import {
  api,
  errorMessage,
  type GameRole,
  type GuildEvent,
  type Placement,
  type Signup,
  type SignupStatus,
} from "@/api/client";
import { KEYS, useCharacters, useEvent, useGameData, useInvalidate } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { KindBadge, StatusBadge } from "@/components/EventBits";
import { ClassDot, ClassName, GameRoleTag } from "@/components/game";
import { Button, Card, Field, Input, PageTitle, Select, Spinner } from "@/components/ui";
import {
  PLACEMENTS,
  PLACEMENT_LABEL,
  SIGNUP_STATUSES,
  SIGNUP_STATUS_LABEL,
  formatLongDate,
  formatTime,
} from "@/lib/events";
import { GAME_ROLES, ROLE_LABEL, findClass, formatDateTime, formatRemaining, toLocalInput } from "@/lib/game";
import { isOfficerOrAbove } from "@/lib/roles";

export function EventPage() {
  const id = Number(useParams().id);
  const event = useEvent(id);
  if (event.isPending) return <Spinner />;
  if (!event.data) return <Navigate to="/agenda" replace />;
  return <EventDetail event={event.data} />;
}

function EventDetail({ event }: { event: GuildEvent }) {
  const me = useCurrentUser();
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const gamedata = useGameData();
  const [error, setError] = useState<string | null>(null);
  const [duplicateAt, setDuplicateAt] = useState<string | null>(null);
  const canManage = event.organizer.id === me.id || isOfficerOrAbove(me.site_role);
  const refresh = () => invalidate(KEYS.event(event.id), KEYS.events);

  const toggleCancel = useMutation({
    mutationFn: async () => {
      const path =
        event.effective_status === "cancelled" ? "/api/events/{id}/restore/" : "/api/events/{id}/cancel/";
      const { error } = await api.POST(path, { params: { path: { id: event.id } } });
      if (error) throw error;
    },
    onSuccess: refresh,
    onError: (e) => setError(errorMessage(e)),
  });

  const duplicate = useMutation({
    mutationFn: async (startsAt: string) => {
      const { data, error } = await api.POST("/api/events/{id}/duplicate/", {
        params: { path: { id: event.id } },
        body: { starts_at: new Date(startsAt).toISOString() },
      });
      if (error || !data) throw error ?? new Error();
      return data;
    },
    onSuccess: async (copy) => {
      await invalidate(KEYS.events);
      navigate(`/agenda/${copy.id}`);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const instance = gamedata.data?.instances.find((i) => i.slug === event.instance);

  return (
    <>
      <PageTitle
        actions={
          <div className="flex flex-wrap gap-2">
            {canManage && (
              <>
                <Link to={`/agenda/${event.id}/modifier`}>
                  <Button variant="ghost">Modifier</Button>
                </Link>
                <Button
                  variant={event.effective_status === "cancelled" ? "ghost" : "danger"}
                  disabled={toggleCancel.isPending}
                  onClick={() => toggleCancel.mutate()}
                >
                  {event.effective_status === "cancelled" ? "Rétablir" : "Annuler"}
                </Button>
              </>
            )}
            <Button
              variant="ghost"
              onClick={() => {
                const next = new Date(event.starts_at);
                next.setDate(next.getDate() + 7);
                setDuplicateAt((v) => (v === null ? toLocalInput(next) : null));
              }}
            >
              Dupliquer
            </Button>
          </div>
        }
      >
        <span className="flex flex-wrap items-center gap-2">
          <KindBadge kind={event.kind} />
          {event.title}
          <StatusBadge status={event.effective_status} />
        </span>
      </PageTitle>

      {duplicateAt !== null && (
        <Card className="mb-4 flex flex-wrap items-end gap-3">
          <Field label="Nouvelle date de début">
            <Input
              type="datetime-local"
              value={duplicateAt}
              onChange={(e) => setDuplicateAt(e.target.value)}
            />
          </Field>
          <Button disabled={duplicate.isPending} onClick={() => duplicate.mutate(duplicateAt)}>
            Créer la copie
          </Button>
          <span className="text-xs text-muted">
            Mêmes réglages, sans les inscriptions, toi comme organisateur.
          </span>
        </Card>
      )}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <div className="space-y-4">
          <Card className="space-y-2 text-sm">
            <p className="font-display text-xl capitalize">{formatLongDate(event.starts_at)}</p>
            <p className="font-mono text-lg">
              {formatTime(event.starts_at)}
              {event.ends_at && ` → ${formatTime(event.ends_at)}`}
            </p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              {instance && (
                <>
                  <dt className="text-muted">Instance</dt>
                  <dd>
                    {instance.name} ({instance.size})
                  </dd>
                </>
              )}
              <dt className="text-muted">Organisateur</dt>
              <dd>
                <Link to={`/membres/${event.organizer.id}`}>{event.organizer.display_name}</Link>
              </dd>
              {event.min_level && (
                <>
                  <dt className="text-muted">Niveau</dt>
                  <dd>{event.min_level} minimum</dd>
                </>
              )}
              <dt className="text-muted">Inscriptions</dt>
              <dd>
                {event.signups_open
                  ? `ouvertes, clôture ${formatRemaining(event.signup_deadline ?? event.starts_at)}`
                  : "closes"}
                {event.signup_deadline && (
                  <span className="text-muted"> ({formatDateTime(event.signup_deadline)})</span>
                )}
              </dd>
            </dl>
            {event.description && (
              <p className="whitespace-pre-wrap border-t border-border pt-2">{event.description}</p>
            )}
          </Card>
          <SignupWidget event={event} onChange={refresh} />
        </div>

        <div className="space-y-4">
          <CompositionBoard event={event} canManage={canManage} onChange={refresh} onError={setError} />
          <SignupList event={event} />
        </div>
      </div>
    </>
  );
}

function SignupWidget({ event, onChange }: { event: GuildEvent; onChange: () => Promise<unknown> }) {
  const me = useCurrentUser();
  const characters = useCharacters();
  const gamedata = useGameData();
  const mine = (characters.data ?? []).filter((c) => c.owner.id === me.id);
  const eligible = mine.filter((c) => !event.min_level || (c.level ?? 1) >= event.min_level);
  const current = event.my_signup;
  const [characterId, setCharacterId] = useState<number>(
    current?.character.id ?? eligible.find((c) => c.is_main)?.id ?? eligible[0]?.id ?? 0,
  );
  const [role, setRole] = useState<GameRole | "">(current?.role ?? "");
  const [status, setStatus] = useState<SignupStatus>(current?.status ?? "present");
  const [comment, setComment] = useState(current?.comment ?? "");
  const [error, setError] = useState<string | null>(null);

  const character = mine.find((c) => c.id === characterId);
  const roles = character ? ([character.main_role, character.off_role].filter(Boolean) as GameRole[]) : [];
  const effectiveRole = roles.includes(role as GameRole) ? (role as GameRole) : roles[0];

  const save = useMutation({
    mutationFn: async () => {
      if (!character || !effectiveRole) throw { detail: "Choisis un personnage." };
      const { error } = await api.POST("/api/events/{id}/signup/", {
        params: { path: { id: event.id } },
        body: { character: character.id, role: effectiveRole, status, comment },
      });
      if (error) throw error;
    },
    onSuccess: () => {
      setError(null);
      return onChange();
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const remove = useMutation({
    mutationFn: async () => {
      const { error } = await api.DELETE("/api/events/{id}/signup/", { params: { path: { id: event.id } } });
      if (error) throw error;
    },
    onSuccess: onChange,
    onError: (e) => setError(errorMessage(e)),
  });

  if (!event.signups_open) {
    return (
      <Card className="text-sm text-muted">
        {current
          ? `Tu es inscrit (${SIGNUP_STATUS_LABEL[current.status]}, ${PLACEMENT_LABEL[current.placement].toLowerCase()}). Les inscriptions sont closes, vois avec l'organisateur pour changer.`
          : "Les inscriptions sont closes."}
      </Card>
    );
  }
  if (mine.length === 0) {
    return (
      <Card className="text-sm text-muted">
        <Link to="/personnages/nouveau">Crée un personnage</Link> pour pouvoir t'inscrire.
      </Card>
    );
  }
  if (eligible.length === 0) {
    return (
      <Card className="text-sm text-muted">
        Aucun de tes personnages n'a le niveau requis ({event.min_level}).
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="mb-3 font-display text-lg">{current ? "Mon inscription" : "Je m'inscris"}</h2>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label="Personnage">
            <Select
              className="w-full"
              value={characterId}
              onChange={(e) => setCharacterId(Number(e.target.value))}
            >
              {eligible.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({findClass(gamedata.data, c.player_class)?.name}, {c.level})
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Rôle">
            <Select
              className="w-full"
              value={effectiveRole ?? ""}
              onChange={(e) => setRole(e.target.value as GameRole)}
            >
              {GAME_ROLES.filter((r) => roles.includes(r)).map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Statut">
          <div className="flex flex-wrap gap-1">
            {SIGNUP_STATUSES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStatus(s)}
                className={clsx(
                  "rounded-md border px-2.5 py-1 text-sm",
                  status === s
                    ? "border-gold bg-gold/15 text-gold"
                    : "border-border text-muted hover:text-text",
                )}
              >
                {SIGNUP_STATUS_LABEL[s]}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Commentaire">
          <Input
            value={comment}
            maxLength={240}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Ex. je ramène les potions"
          />
        </Field>
        <div className="flex items-center gap-2">
          <Button type="submit" disabled={save.isPending}>
            {current ? "Mettre à jour" : "M'inscrire"}
          </Button>
          {current && (
            <Button
              type="button"
              variant="danger"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              Me désinscrire
            </Button>
          )}
        </div>
        {error && <p className="text-sm text-danger">{error}</p>}
        {current && (
          <p className="text-xs text-muted">
            Placement : <strong>{PLACEMENT_LABEL[current.placement]}</strong>
          </p>
        )}
      </form>
    </Card>
  );
}

function CompositionBoard({
  event,
  canManage,
  onChange,
  onError,
}: {
  event: GuildEvent;
  canManage: boolean;
  onChange: () => Promise<unknown>;
  onError: (message: string) => void;
}) {
  const gamedata = useGameData();
  const place = useMutation({
    mutationFn: async ({ signup, placement }: { signup: Signup; placement: Placement }) => {
      const { error } = await api.PATCH("/api/signups/{id}/", {
        params: { path: { id: signup.id } },
        body: { placement },
      });
      if (error) throw error;
    },
    onSuccess: onChange,
    onError: (e) => onError(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: async (signup: Signup) => {
      const { error } = await api.DELETE("/api/signups/{id}/", { params: { path: { id: signup.id } } });
      if (error) throw error;
    },
    onSuccess: onChange,
    onError: (e) => onError(errorMessage(e)),
  });

  const candidates = event.signups.filter((s) => s.status !== "absent");
  const needs: Record<GameRole, number | null | undefined> = {
    tank: event.need_tanks,
    heal: event.need_heals,
    dps: event.need_dps,
  };

  const renderSignup = (signup: Signup) => {
    const playerClass = findClass(gamedata.data, signup.character.player_class);
    return (
      <li key={signup.id} className="flex items-center gap-2 text-sm">
        <ClassDot playerClass={playerClass} />
        <Link to={`/personnages/${signup.character.id}`} className="truncate">
          <ClassName playerClass={playerClass}>{signup.character.name}</ClassName>
        </Link>
        <span className="font-mono text-xs text-muted">{signup.character.level}</span>
        {signup.status !== "present" && (
          <span className="text-xs text-muted">({SIGNUP_STATUS_LABEL[signup.status]})</span>
        )}
        {canManage && event.effective_status === "planned" && (
          <span className="ml-auto flex items-center gap-1">
            <Select
              value={signup.placement}
              aria-label={`Placement de ${signup.character.name}`}
              disabled={place.isPending}
              onChange={(e) => place.mutate({ signup, placement: e.target.value as Placement })}
              className="py-0.5 text-xs"
            >
              {PLACEMENTS.map((p) => (
                <option key={p} value={p}>
                  {PLACEMENT_LABEL[p]}
                </option>
              ))}
            </Select>
            <button
              type="button"
              aria-label="Retirer"
              className="px-1 text-xs text-muted hover:text-danger"
              onClick={() => {
                if (window.confirm(`Retirer ${signup.character.name} ?`)) remove.mutate(signup);
              }}
            >
              ✕
            </button>
          </span>
        )}
      </li>
    );
  };

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-lg">Composition</h2>
        <span className="text-xs text-muted">
          {canManage ? "Place les candidats en confirmé ou sur le banc." : "Validée par l'organisateur."}
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {GAME_ROLES.map((role) => {
          const confirmed = candidates.filter((s) => s.role === role && s.placement === "confirmed");
          const waiting = candidates.filter((s) => s.role === role && s.placement === "unplaced");
          const bench = candidates.filter((s) => s.role === role && s.placement === "bench");
          const need = needs[role];
          return (
            <div key={role} className="rounded-md border border-border bg-bg/60 p-3">
              <div className="mb-2 flex items-baseline justify-between">
                <GameRoleTag role={role} />
                <span
                  className={clsx(
                    "font-mono text-sm",
                    need != null && confirmed.length >= need ? "text-success" : "text-muted",
                  )}
                >
                  {confirmed.length}
                  {need != null && ` / ${need}`}
                </span>
              </div>
              <ul className="space-y-1">{confirmed.map(renderSignup)}</ul>
              {waiting.length > 0 && (
                <>
                  <p className="mt-3 text-xs uppercase text-muted">Candidats</p>
                  <ul className="mt-1 space-y-1">{waiting.map(renderSignup)}</ul>
                </>
              )}
              {bench.length > 0 && (
                <>
                  <p className="mt-3 text-xs uppercase text-muted">Banc</p>
                  <ul className="mt-1 space-y-1 opacity-70">{bench.map(renderSignup)}</ul>
                </>
              )}
              {confirmed.length + waiting.length + bench.length === 0 && (
                <p className="text-xs text-muted">Personne</p>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function SignupList({ event }: { event: GuildEvent }) {
  if (event.signups.length === 0) return null;
  return (
    <Card>
      <h2 className="mb-3 font-display text-lg">Inscrits ({event.signups.length})</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {SIGNUP_STATUSES.map((status) => {
          const list = event.signups.filter((s) => s.status === status);
          if (list.length === 0) return null;
          return (
            <div key={status}>
              <p className="text-xs uppercase text-muted">
                {SIGNUP_STATUS_LABEL[status]} ({list.length})
              </p>
              <ul className="mt-1 space-y-1 text-sm">
                {list.map((s) => (
                  <li key={s.id}>
                    <Link to={`/membres/${s.user.id}`} className="text-text hover:text-gold">
                      {s.user.display_name}
                    </Link>
                    <span className="text-muted">
                      {" "}
                      · {s.character.name} · {ROLE_LABEL[s.role]}
                    </span>
                    {s.comment && <span className="block text-xs text-muted">« {s.comment} »</span>}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
