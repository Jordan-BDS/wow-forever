import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router";
import {
  api,
  fieldErrors,
  type Character,
  type CharacterProfessionRequest,
  type GameRole,
} from "@/api/client";
import { useGuild } from "@/api/guild";
import { KEYS, useCharacters, useGameData, useInvalidate } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Button, Card, Field, Input, PageTitle, Select, Spinner } from "@/components/ui";
import { GAME_ROLES, ROLE_LABEL, findClass, racesFor } from "@/lib/game";
import { isOfficerOrAbove } from "@/lib/roles";

interface FormState {
  name: string;
  surname: string;
  player_class: string;
  race: string;
  level: number;
  main_role: GameRole | "";
  off_role: GameRole | "";
  specialization: string;
  is_main: boolean;
  note: string;
  professions: { profession: string; skill: number; specialization: string }[];
}

const EMPTY: FormState = {
  name: "",
  surname: "",
  player_class: "",
  race: "",
  level: 1,
  main_role: "",
  off_role: "",
  specialization: "",
  is_main: false,
  note: "",
  professions: [],
};

function fromCharacter(c: Character): FormState {
  return {
    name: c.name,
    surname: c.surname ?? "",
    player_class: c.player_class,
    race: c.race,
    level: c.level ?? 1,
    main_role: c.main_role,
    off_role: (c.off_role as GameRole | "") ?? "",
    specialization: c.specialization ?? "",
    is_main: c.is_main ?? false,
    note: c.note ?? "",
    professions: (c.professions ?? []).map((p) => ({
      profession: p.profession,
      skill: p.skill ?? 1,
      specialization: p.specialization ?? "",
    })),
  };
}

export function CharacterFormPage() {
  const { id } = useParams();
  const characterId = id ? Number(id) : undefined;
  const characters = useCharacters();
  const me = useCurrentUser();

  if (characterId !== undefined) {
    if (characters.isPending) return <Spinner />;
    const existing = characters.data?.find((c) => c.id === characterId);
    if (!existing) return <Navigate to="/roster" replace />;
    if (existing.owner.id !== me.id && !isOfficerOrAbove(me.site_role)) {
      return <Navigate to={`/personnages/${characterId}`} replace />;
    }
    return <CharacterForm key={existing.id} characterId={characterId} initial={fromCharacter(existing)} />;
  }
  return <CharacterForm initial={EMPTY} />;
}

function CharacterForm({ characterId, initial }: { characterId?: number; initial: FormState }) {
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const gamedata = useGameData();
  const guild = useGuild();
  const [form, setForm] = useState<FormState>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const save = useMutation({
    mutationFn: async (state: FormState) => {
      const body = {
        name: state.name.trim(),
        surname: state.surname.trim(),
        player_class: state.player_class,
        race: state.race,
        level: state.level,
        main_role: state.main_role as GameRole,
        off_role: state.off_role,
        specialization: state.specialization || null,
        is_main: state.is_main,
        note: state.note,
        professions: state.professions.map<CharacterProfessionRequest>((p) => ({
          profession: p.profession,
          skill: p.skill,
          specialization: p.specialization || null,
        })),
      };
      if (characterId === undefined) {
        const { data, error } = await api.POST("/api/characters/", { body });
        if (error || !data) throw error ?? new Error();
        return data;
      }
      const { data, error } = await api.PATCH("/api/characters/{id}/", {
        params: { path: { id: characterId } },
        body,
      });
      if (error || !data) throw error ?? new Error();
      return data;
    },
    onSuccess: async (character) => {
      await invalidate(KEYS.characters);
      navigate(`/personnages/${character.id}`);
    },
    onError: (e) => setErrors(fieldErrors(e)),
  });

  if (gamedata.isPending || guild.isPending) return <Spinner />;
  const data = gamedata.data;
  const playerClass = findClass(data, form.player_class);
  const races = form.player_class ? racesFor(data, form.player_class, guild.data?.faction ?? "") : [];
  const allowedRoles = playerClass?.roles ?? [];
  const professions = data?.professions ?? [];
  const primaryCount = form.professions.filter(
    (p) => professions.find((x) => x.slug === p.profession)?.kind === "primary",
  ).length;

  const update = (patch: Partial<FormState>) => setForm((prev) => ({ ...prev, ...patch }));

  const onClassChange = (slug: string) => {
    const cls = findClass(data, slug);
    const roles = cls?.roles ?? [];
    update({
      player_class: slug,
      race: racesFor(data, slug, guild.data?.faction ?? "").some((r) => r.slug === form.race)
        ? form.race
        : "",
      main_role:
        roles.length === 1 ? (roles[0] as GameRole) : roles.includes(form.main_role) ? form.main_role : "",
      off_role: roles.includes(form.off_role) && form.off_role !== form.main_role ? form.off_role : "",
      specialization: "",
    });
  };

  const setProfession = (index: number, patch: Partial<FormState["professions"][number]>) =>
    update({ professions: form.professions.map((p, i) => (i === index ? { ...p, ...patch } : p)) });

  return (
    <>
      <PageTitle>{characterId === undefined ? "Nouveau personnage" : `Modifier ${initial.name}`}</PageTitle>
      <form
        className="grid gap-4 lg:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          save.mutate(form);
        }}
      >
        <Card className="space-y-4">
          <h2 className="font-display text-lg">Identité</h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Prénom du personnage">
              <Input
                value={form.name}
                maxLength={24}
                required
                onChange={(e) => update({ name: e.target.value })}
              />
              <FieldError message={errors.name} />
            </Field>
            <Field label="Nom de famille (Forever)">
              <Input
                value={form.surname}
                maxLength={24}
                placeholder="Rempli par l'addon"
                onChange={(e) => update({ surname: e.target.value })}
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Classe">
              <Select
                className="w-full"
                value={form.player_class}
                required
                onChange={(e) => onClassChange(e.target.value)}
              >
                <option value="">—</option>
                {data?.classes.map((c) => (
                  <option key={c.slug} value={c.slug}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Race">
              <Select
                className="w-full"
                value={form.race}
                required
                disabled={!form.player_class}
                onChange={(e) => update({ race: e.target.value })}
              >
                <option value="">—</option>
                {races.map((r) => (
                  <option key={r.slug} value={r.slug}>
                    {r.name}
                  </option>
                ))}
              </Select>
              <FieldError message={errors.race} />
            </Field>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Niveau">
              <Input
                type="number"
                min={1}
                max={60}
                value={form.level}
                onChange={(e) => update({ level: Number(e.target.value) })}
              />
              <FieldError message={errors.level} />
            </Field>
            <Field label="Rôle principal">
              <Select
                className="w-full"
                value={form.main_role}
                required
                disabled={!playerClass}
                onChange={(e) => update({ main_role: e.target.value as GameRole })}
              >
                <option value="">—</option>
                {GAME_ROLES.filter((r) => allowedRoles.includes(r)).map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABEL[r]}
                  </option>
                ))}
              </Select>
              <FieldError message={errors.main_role} />
            </Field>
            <Field label="Rôle secondaire">
              <Select
                className="w-full"
                value={form.off_role}
                disabled={!playerClass}
                onChange={(e) => update({ off_role: e.target.value as GameRole | "" })}
              >
                <option value="">Aucun</option>
                {GAME_ROLES.filter((r) => allowedRoles.includes(r) && r !== form.main_role).map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABEL[r]}
                  </option>
                ))}
              </Select>
              <FieldError message={errors.off_role} />
            </Field>
          </div>
          <Field label="Spécialisation">
            <Select
              className="w-full"
              value={form.specialization}
              disabled={!playerClass}
              onChange={(e) => update({ specialization: e.target.value })}
            >
              <option value="">Pas encore choisie</option>
              {playerClass?.specializations.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.name}
                </option>
              ))}
            </Select>
            <FieldError message={errors.specialization} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_main}
              onChange={(e) => update({ is_main: e.target.checked })}
              className="accent-gold"
            />
            C'est mon main
            <span className="text-xs text-muted">(ton premier perso le devient automatiquement)</span>
          </label>
          <Field label="Note">
            <textarea
              value={form.note}
              rows={2}
              onChange={(e) => update({ note: e.target.value })}
              className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm focus:border-gold focus:outline-none"
            />
          </Field>
        </Card>

        <Card className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg">Métiers</h2>
            <span className="text-xs text-muted">{primaryCount}/2 principaux</span>
          </div>
          {form.professions.map((row, index) => {
            const profession = professions.find((p) => p.slug === row.profession);
            return (
              <div
                key={index}
                className="grid grid-cols-[1fr_80px_auto] items-end gap-2 sm:grid-cols-[1fr_80px_1fr_auto]"
              >
                <Field label="Métier">
                  <Select
                    className="w-full"
                    value={row.profession}
                    onChange={(e) => setProfession(index, { profession: e.target.value, specialization: "" })}
                  >
                    {professions.map((p) => {
                      const taken = form.professions.some((x, i) => i !== index && x.profession === p.slug);
                      const primaryFull =
                        p.kind === "primary" && profession?.kind !== "primary" && primaryCount >= 2;
                      return (
                        <option key={p.slug} value={p.slug} disabled={taken || primaryFull}>
                          {p.name}
                          {p.kind === "secondary" && " (secondaire)"}
                        </option>
                      );
                    })}
                  </Select>
                </Field>
                <Field label="Niveau">
                  <Input
                    type="number"
                    min={1}
                    max={300}
                    value={row.skill}
                    onChange={(e) => setProfession(index, { skill: Number(e.target.value) })}
                  />
                </Field>
                <div className="order-last col-span-full sm:order-none sm:col-auto">
                  <Field label="Spécialisation">
                    <Select
                      className="w-full"
                      value={row.specialization}
                      disabled={!profession?.specializations.length}
                      onChange={(e) => setProfession(index, { specialization: e.target.value })}
                    >
                      <option value="">—</option>
                      {profession?.specializations.map((s) => (
                        <option key={s.slug} value={s.slug}>
                          {s.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label="Retirer ce métier"
                  onClick={() => update({ professions: form.professions.filter((_, i) => i !== index) })}
                >
                  ✕
                </Button>
              </div>
            );
          })}
          <FieldError message={errors.professions} />
          <Button
            type="button"
            variant="ghost"
            disabled={form.professions.length >= professions.length}
            onClick={() => {
              const next = professions.find(
                (p) =>
                  !form.professions.some((x) => x.profession === p.slug) &&
                  (p.kind === "secondary" || primaryCount < 2),
              );
              if (next)
                update({
                  professions: [...form.professions, { profession: next.slug, skill: 1, specialization: "" }],
                });
            }}
          >
            + Ajouter un métier
          </Button>
        </Card>

        <div className="flex items-center gap-3 lg:col-span-2">
          <Button type="submit" disabled={save.isPending}>
            {characterId === undefined ? "Créer le personnage" : "Enregistrer"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
            Annuler
          </Button>
          {errors.detail && <span className="text-sm text-danger">{errors.detail}</span>}
          {errors.non_field_errors && <span className="text-sm text-danger">{errors.non_field_errors}</span>}
        </div>
      </form>
    </>
  );
}

function FieldError({ message }: { message?: string }) {
  return message ? <p className="text-xs text-danger">{message}</p> : null;
}
