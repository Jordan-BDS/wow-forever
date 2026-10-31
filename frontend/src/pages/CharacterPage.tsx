import { useMutation } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { api, errorMessage, type GameRole } from "@/api/client";
import {
  KEYS,
  useCharacters,
  useEquipmentSets,
  useGameData,
  useInvalidate,
  useTalentBuilds,
} from "@/api/hooks";
import { EquipmentPanel } from "@/components/EquipmentPanel";
import { ProgressPanel } from "@/components/ProgressPanel";
import { RecipesPanel } from "@/components/RecipesPanel";
import { TalentPanel } from "@/components/TalentPanel";
import clsx from "clsx";
import { useState } from "react";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { ClassName, GameRoleTag, LevelBadge } from "@/components/game";
import { RolesToConfirmBadge, SyncBadge } from "@/components/SyncBadge";
import { Button, Card, PageTitle, Spinner } from "@/components/ui";
import { findClass, findRace, specName } from "@/lib/game";
import { isOfficerOrAbove } from "@/lib/roles";

export function CharacterPage() {
  const id = Number(useParams().id);
  const me = useCurrentUser();
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const characters = useCharacters();
  const gamedata = useGameData();
  const sets = useEquipmentSets(id);
  const builds = useTalentBuilds(id);
  const [activeTab, setTab] = useState<"equipment" | "talents" | "recipes" | "progress">("equipment");

  const setMain = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/characters/{id}/set-main/", { params: { path: { id } } });
      if (error) throw error;
    },
    onSuccess: () => invalidate(KEYS.characters),
  });

  const remove = useMutation({
    mutationFn: async () => {
      const { error } = await api.DELETE("/api/characters/{id}/", { params: { path: { id } } });
      if (error) throw error;
    },
    onSuccess: async () => {
      await invalidate(KEYS.characters);
      navigate("/roster");
    },
  });

  if (characters.isPending || gamedata.isPending) return <Spinner />;
  const character = characters.data?.find((c) => c.id === id);
  if (!character) return <Navigate to="/roster" replace />;

  const playerClass = findClass(gamedata.data, character.player_class);
  const race = findRace(gamedata.data, character.race);
  const canEdit = character.owner.id === me.id || isOfficerOrAbove(me.site_role);
  const professions = gamedata.data?.professions ?? [];

  return (
    <>
      <PageTitle
        actions={
          canEdit && (
            <div className="flex flex-wrap gap-2">
              {!character.is_main && (
                <Button variant="ghost" disabled={setMain.isPending} onClick={() => setMain.mutate()}>
                  Définir comme main
                </Button>
              )}
              <Link to={`/personnages/${id}/modifier`}>
                <Button variant="ghost">Modifier</Button>
              </Link>
              <Button
                variant="danger"
                disabled={remove.isPending}
                onClick={() => {
                  if (window.confirm(`Supprimer ${character.name} ?`)) remove.mutate();
                }}
              >
                Supprimer
              </Button>
            </div>
          )
        }
      >
        <ClassName playerClass={playerClass}>{character.full_name || character.name}</ClassName>
        {character.is_main && <span className="ml-2 text-sm text-muted">main</span>}
        <span className="ml-3 inline-flex items-center gap-2 align-middle">
          <SyncBadge character={character} />
          <RolesToConfirmBadge character={character} />
        </span>
      </PageTitle>
      {(setMain.error || remove.error) && (
        <p className="mb-4 text-sm text-danger">{errorMessage(setMain.error ?? remove.error)}</p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="font-display text-lg">Personnage</h2>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
            <dt className="text-muted">Joueur</dt>
            <dd>
              <Link to={`/membres/${character.owner.id}`}>{character.owner.display_name}</Link>
            </dd>
            <dt className="text-muted">Classe</dt>
            <dd>
              <ClassName playerClass={playerClass}>{playerClass?.name}</ClassName>
            </dd>
            <dt className="text-muted">Race</dt>
            <dd>{race?.name}</dd>
            <dt className="text-muted">Niveau</dt>
            <dd>
              <LevelBadge level={character.level ?? 1} />
            </dd>
            <dt className="text-muted">Rôles</dt>
            <dd>
              <GameRoleTag role={character.main_role} />
              {character.off_role && (
                <>
                  <span className="text-muted"> / </span>
                  <GameRoleTag role={character.off_role as GameRole} muted />
                </>
              )}
            </dd>
            <dt className="text-muted">Spécialisation</dt>
            <dd>
              {specName(gamedata.data, character.specialization) || (
                <em className="text-muted">non choisie</em>
              )}
            </dd>
            {character.note && (
              <>
                <dt className="text-muted">Note</dt>
                <dd className="whitespace-pre-wrap">{character.note}</dd>
              </>
            )}
          </dl>
        </Card>
        <Card>
          <h2 className="font-display text-lg">Métiers</h2>
          {character.professions?.length ? (
            <ul className="mt-3 space-y-2 text-sm">
              {character.professions.map((p) => {
                const profession = professions.find((x) => x.slug === p.profession);
                const spec = profession?.specializations.find((s) => s.slug === p.specialization);
                return (
                  <li key={p.profession} className="flex items-center justify-between">
                    <span>
                      {profession?.name ?? p.profession}
                      {spec && <span className="text-muted"> · {spec.name}</span>}
                    </span>
                    <span className="font-mono text-muted">{p.skill}/300</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-muted">Aucun métier renseigné.</p>
          )}
        </Card>
        <div className="md:col-span-2">
          <div className="nav-scroll -mx-4 mb-3 flex gap-1 overflow-x-auto border-b border-border px-4 text-sm sm:mx-0 sm:px-0">
            {(["equipment", "talents", "recipes", "progress"] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setTab(tab)}
                className={clsx(
                  "-mb-px whitespace-nowrap border-b-2 px-3 py-2",
                  activeTab === tab
                    ? "border-gold text-gold"
                    : "border-transparent text-muted hover:text-text",
                )}
              >
                {tab === "equipment"
                  ? "Équipement et stats"
                  : tab === "talents"
                    ? "Talents"
                    : tab === "recipes"
                      ? "Recettes"
                      : "Progression"}
              </button>
            ))}
          </div>
          {activeTab === "equipment" ? (
            sets.isPending ? (
              <Spinner />
            ) : (
              <EquipmentPanel character={character} sets={sets.data ?? []} canEdit={canEdit} />
            )
          ) : activeTab === "talents" ? (
            builds.isPending ? (
              <Spinner />
            ) : (
              <TalentPanel character={character} builds={builds.data ?? []} canEdit={canEdit} />
            )
          ) : activeTab === "recipes" ? (
            <RecipesPanel character={character} canEdit={canEdit} />
          ) : (
            <ProgressPanel character={character} />
          )}
        </div>
      </div>
    </>
  );
}
