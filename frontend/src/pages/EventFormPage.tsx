import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router";
import { api, fieldErrors, type EventKind, type GuildEvent } from "@/api/client";
import { KEYS, useEvent, useGameData, useInvalidate } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Button, Card, Field, Input, PageTitle, Select, Spinner } from "@/components/ui";
import { EVENT_KINDS, EVENT_KIND_LABEL, instancesFor } from "@/lib/events";
import { toLocalInput } from "@/lib/game";
import { isOfficerOrAbove } from "@/lib/roles";

interface FormState {
  title: string;
  kind: EventKind;
  instance: string;
  starts_at: string;
  ends_at: string;
  description: string;
  max_size: string;
  need_tanks: string;
  need_heals: string;
  need_dps: string;
  min_level: string;
  signup_deadline: string;
}

function nextEvening(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(20, 30, 0, 0);
  return toLocalInput(d);
}

function emptyForm(): FormState {
  return {
    title: "",
    kind: "dungeon",
    instance: "",
    starts_at: nextEvening(),
    ends_at: "",
    description: "",
    max_size: "",
    need_tanks: "",
    need_heals: "",
    need_dps: "",
    min_level: "",
    signup_deadline: "",
  };
}

const str = (v: number | null | undefined) => (v == null ? "" : String(v));

function fromEvent(e: GuildEvent): FormState {
  return {
    title: e.title,
    kind: e.kind,
    instance: e.instance ?? "",
    starts_at: toLocalInput(e.starts_at),
    ends_at: e.ends_at ? toLocalInput(e.ends_at) : "",
    description: e.description ?? "",
    max_size: str(e.max_size),
    need_tanks: str(e.need_tanks),
    need_heals: str(e.need_heals),
    need_dps: str(e.need_dps),
    min_level: str(e.min_level),
    signup_deadline: e.signup_deadline ? toLocalInput(e.signup_deadline) : "",
  };
}

export function EventFormPage() {
  const { id } = useParams();
  if (id) return <EditEvent id={Number(id)} />;
  return <EventForm initial={emptyForm()} />;
}

function EditEvent({ id }: { id: number }) {
  const me = useCurrentUser();
  const event = useEvent(id);
  if (event.isPending) return <Spinner />;
  if (!event.data) return <Navigate to="/agenda" replace />;
  if (event.data.organizer.id !== me.id && !isOfficerOrAbove(me.site_role)) {
    return <Navigate to={`/agenda/${id}`} replace />;
  }
  return <EventForm key={event.data.updated_at} eventId={id} initial={fromEvent(event.data)} />;
}

function EventForm({ eventId, initial }: { eventId?: number; initial: FormState }) {
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const gamedata = useGameData();
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const save = useMutation({
    mutationFn: async () => {
      const num = (v: string) => (v === "" ? null : Number(v));
      const iso = (v: string) => (v === "" ? null : new Date(v).toISOString());
      const body = {
        title: form.title.trim(),
        kind: form.kind,
        instance: form.instance || null,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: iso(form.ends_at),
        description: form.description,
        max_size: num(form.max_size),
        need_tanks: num(form.need_tanks),
        need_heals: num(form.need_heals),
        need_dps: num(form.need_dps),
        min_level: num(form.min_level),
        signup_deadline: iso(form.signup_deadline),
      };
      if (eventId === undefined) {
        const { data, error } = await api.POST("/api/events/", { body });
        if (error || !data) throw error ?? new Error();
        return data;
      }
      const { data, error } = await api.PATCH("/api/events/{id}/", {
        params: { path: { id: eventId } },
        body,
      });
      if (error || !data) throw error ?? new Error();
      return data;
    },
    onSuccess: async (event) => {
      await invalidate(KEYS.events);
      navigate(`/agenda/${event.id}`);
    },
    onError: (e) => setErrors(fieldErrors(e)),
  });

  if (gamedata.isPending) return <Spinner />;
  const instances = instancesFor(gamedata.data?.instances, form.kind);
  const update = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));

  const onKindChange = (kind: EventKind) => {
    const stillValid = instancesFor(gamedata.data?.instances, kind).some((i) => i.slug === form.instance);
    update({ kind, instance: stillValid ? form.instance : "" });
  };

  /** Pré-remplit titre, taille, besoins et niveau depuis l'instance choisie. */
  const onInstanceChange = (slug: string) => {
    const previous = instances.find((i) => i.slug === form.instance);
    const instance = instances.find((i) => i.slug === slug);
    const patch: Partial<FormState> = { instance: slug };
    if (instance) {
      if (!form.title.trim() || form.title === previous?.name) patch.title = instance.name;
      patch.max_size = String(instance.size);
      patch.need_tanks = str(instance.default_tanks);
      patch.need_heals = str(instance.default_heals);
      patch.need_dps = str(instance.default_dps);
      patch.min_level = String(instance.min_level);
    }
    update(patch);
  };

  return (
    <>
      <PageTitle>{eventId === undefined ? "Nouvel événement" : `Modifier « ${initial.title} »`}</PageTitle>
      <form
        className="grid gap-4 lg:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          save.mutate();
        }}
      >
        <Card className="space-y-4">
          <h2 className="font-display text-lg">Quoi</h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Type">
              <Select
                className="w-full"
                value={form.kind}
                onChange={(e) => onKindChange(e.target.value as EventKind)}
              >
                {EVENT_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {EVENT_KIND_LABEL[k]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Instance">
              <Select
                className="w-full"
                value={form.instance}
                disabled={instances.length === 0}
                onChange={(e) => onInstanceChange(e.target.value)}
              >
                <option value="">{instances.length ? "—" : "Sans instance"}</option>
                {instances.map((i) => (
                  <option key={i.slug} value={i.slug}>
                    {i.name} ({i.size})
                  </option>
                ))}
              </Select>
              <FieldError message={errors.instance} />
            </Field>
          </div>
          <Field label="Titre">
            <Input
              value={form.title}
              required
              maxLength={120}
              onChange={(e) => update({ title: e.target.value })}
            />
            <FieldError message={errors.title} />
          </Field>
          <Field label="Description (consignes, prérequis, consommables…)">
            <textarea
              value={form.description}
              rows={5}
              onChange={(e) => update({ description: e.target.value })}
              className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm focus:border-gold focus:outline-none"
            />
          </Field>
        </Card>

        <Card className="space-y-4">
          <h2 className="font-display text-lg">Quand et combien</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Début">
              <Input
                type="datetime-local"
                value={form.starts_at}
                required
                onChange={(e) => update({ starts_at: e.target.value })}
              />
              <FieldError message={errors.starts_at} />
            </Field>
            <Field label="Fin (facultative)">
              <Input
                type="datetime-local"
                value={form.ends_at}
                onChange={(e) => update({ ends_at: e.target.value })}
              />
              <FieldError message={errors.ends_at} />
            </Field>
          </div>
          <Field label="Clôture des inscriptions (facultative, sinon au début)">
            <Input
              type="datetime-local"
              value={form.signup_deadline}
              onChange={(e) => update({ signup_deadline: e.target.value })}
            />
            <FieldError message={errors.signup_deadline} />
          </Field>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Field label="Taille max">
              <Input
                type="number"
                min={1}
                value={form.max_size}
                onChange={(e) => update({ max_size: e.target.value })}
              />
            </Field>
            <Field label="Niveau min">
              <Input
                type="number"
                min={1}
                max={60}
                value={form.min_level}
                onChange={(e) => update({ min_level: e.target.value })}
              />
              <FieldError message={errors.min_level} />
            </Field>
            <Field label="Tanks">
              <Input
                type="number"
                min={0}
                value={form.need_tanks}
                onChange={(e) => update({ need_tanks: e.target.value })}
              />
            </Field>
            <Field label="Heals">
              <Input
                type="number"
                min={0}
                value={form.need_heals}
                onChange={(e) => update({ need_heals: e.target.value })}
              />
            </Field>
            <Field label="DPS">
              <Input
                type="number"
                min={0}
                value={form.need_dps}
                onChange={(e) => update({ need_dps: e.target.value })}
              />
            </Field>
          </div>
          <p className="text-xs text-muted">
            Heures de Paris. Choisir une instance pré-remplit taille, besoins et niveau.
          </p>
        </Card>

        <div className="flex items-center gap-3 lg:col-span-2">
          <Button type="submit" disabled={save.isPending}>
            {eventId === undefined ? "Créer l'événement" : "Enregistrer"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
            Annuler
          </Button>
          <FieldError message={errors.detail} />
          <FieldError message={errors.non_field_errors} />
        </div>
      </form>
    </>
  );
}

function FieldError({ message }: { message?: string }) {
  return message ? <p className="text-xs text-danger">{message}</p> : null;
}
