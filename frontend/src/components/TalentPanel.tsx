import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { api, errorMessage, type Character, type TalentBuild } from "@/api/client";
import { KEYS, useClassTalents, useInvalidate } from "@/api/hooks";
import { TalentTrees } from "@/components/TalentTrees";
import { Button, Card, Input, Spinner } from "@/components/ui";
import {
  MAX_POINTS,
  acquiredAtLevel,
  countsFromOrder,
  dominantTree,
  encodeBuild,
  removeLast,
} from "@/lib/talents";
import { useWowheadTooltips } from "@/lib/wowhead";

interface Props {
  character: Character;
  builds: TalentBuild[];
  canEdit: boolean;
}

export function TalentPanel({ character, builds, canEdit }: Props) {
  const invalidate = useInvalidate();
  const talents = useClassTalents(character.player_class);
  const trees = useMemo(
    () => [...(talents.data?.trees ?? [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    [talents.data],
  );
  const [selectedId, setSelectedId] = useState<number | null>(
    builds.find((b) => b.is_active)?.id ?? builds[0]?.id ?? null,
  );
  const selected = builds.find((b) => b.id === selectedId) ?? builds.find((b) => b.is_active) ?? builds[0];
  const [points, setPoints] = useState<number[]>(selected?.points ?? []);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);

  // Resynchronise l'état local quand le build sélectionné change (ajustement d'état pendant le rendu).
  const syncKey = `${selected?.id}:${selected?.updated_at}`;
  const [syncedKey, setSyncedKey] = useState(syncKey);
  // Les points qui ne sont pas des talents de la classe (ancien build d'une autre classe) sont ignorés.
  const knownIds = useMemo(() => new Set(trees.flatMap((t) => t.talents.map((x) => x.id))), [trees]);
  const cleanPoints = (list: number[]) => (knownIds.size ? list.filter((id) => knownIds.has(id)) : list);
  if (syncKey !== syncedKey) {
    setSyncedKey(syncKey);
    setPoints(cleanPoints(selected?.points ?? []));
    setError(null);
  }
  useWowheadTooltips([trees, selected?.id]);

  const refresh = () => invalidate(KEYS.talentBuilds(character.id), KEYS.characters);
  const base = { params: { path: { character_pk: character.id, id: String(selected?.id ?? 0) } } };

  const save = useMutation({
    mutationFn: async (next: number[]) => {
      if (!selected) return;
      const { error } = await api.PATCH("/api/characters/{character_pk}/talent-builds/{id}/", {
        ...base,
        body: { points: next },
      });
      if (error) throw error;
    },
    onSuccess: () => {
      setError(null);
      return refresh();
    },
    onError: (e) => {
      setError(errorMessage(e));
      setPoints(cleanPoints(selected?.points ?? [])); // le clic refusé est annulé
    },
  });

  const create = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/characters/{character_pk}/talent-builds/", {
        params: { path: { character_pk: character.id } },
        body: { name: `Build ${builds.length + 1}`, points: [] },
      });
      if (error || !data) throw error ?? new Error();
      return data;
    },
    onSuccess: async (build) => {
      await refresh();
      setSelectedId(build.id);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const action = useMutation({
    mutationFn: async ({ kind, name }: { kind: "activate" | "rename" | "delete"; name?: string }) => {
      if (!selected) return;
      if (kind === "activate") {
        const { error } = await api.POST("/api/characters/{character_pk}/talent-builds/{id}/activate/", base);
        if (error) throw error;
      } else if (kind === "rename") {
        const { error } = await api.PATCH("/api/characters/{character_pk}/talent-builds/{id}/", {
          ...base,
          body: { name },
        });
        if (error) throw error;
      } else {
        const { error } = await api.DELETE("/api/characters/{character_pk}/talent-builds/{id}/", base);
        if (error) throw error;
        setSelectedId(null);
      }
    },
    onSuccess: () => {
      setRenaming(null);
      return refresh();
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const update = (next: number[]) => {
    const cleaned = cleanPoints(next); // les arbres peuvent arriver après la synchronisation initiale
    setPoints(cleaned);
    save.mutate(cleaned);
  };

  const build = countsFromOrder(cleanPoints(points));
  const acquiredCount = Math.min(points.length, acquiredAtLevel(character.level ?? 1));
  const acquired = countsFromOrder(points.slice(0, acquiredCount));
  const dominant = dominantTree(trees, acquired);
  const shareLink = trees.length ? `/talents?c=${character.player_class}&t=${encodeBuild(trees, build)}` : "";

  if (talents.isPending) return <Spinner />;

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-2 text-sm">
        {builds.length === 0 && <span className="text-muted">Aucun build pour l'instant.</span>}
        {builds.map((b) => (
          <button
            key={b.id}
            type="button"
            onClick={() => setSelectedId(b.id)}
            className={
              b.id === selected?.id
                ? "rounded-md border border-gold bg-gold/10 px-3 py-1 text-gold"
                : "rounded-md border border-border px-3 py-1 text-muted hover:text-text"
            }
          >
            {b.name}
            {b.is_active && " ★"}
          </button>
        ))}
        {canEdit && (
          <Button variant="ghost" disabled={create.isPending} onClick={() => create.mutate()}>
            + Nouveau build
          </Button>
        )}
        {selected && (
          <span className="ml-auto flex flex-wrap items-center gap-2">
            <span className="text-muted">
              {acquiredCount} acquis
              {points.length > acquiredCount && ` + ${points.length - acquiredCount} projetés`} / {MAX_POINTS}
              {dominant && ` · ${dominant.name}`}
            </span>
            {shareLink && (
              <Link to={shareLink} className="text-xs">
                Lien partageable
              </Link>
            )}
            {canEdit && !selected.is_active && (
              <Button variant="ghost" onClick={() => action.mutate({ kind: "activate" })}>
                Activer
              </Button>
            )}
            {canEdit && renaming === null && (
              <Button variant="ghost" onClick={() => setRenaming(selected.name)}>
                Renommer
              </Button>
            )}
            {canEdit && points.length > 0 && (
              <Button variant="ghost" onClick={() => update([])}>
                Vider
              </Button>
            )}
            {canEdit && (
              <Button
                variant="danger"
                onClick={() => {
                  if (window.confirm(`Supprimer le build « ${selected.name} » ?`))
                    action.mutate({ kind: "delete" });
                }}
              >
                Supprimer
              </Button>
            )}
          </span>
        )}
        {renaming !== null && (
          <form
            className="flex w-full items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              action.mutate({ kind: "rename", name: renaming.trim() });
            }}
          >
            <Input
              value={renaming}
              maxLength={40}
              autoFocus
              onChange={(e) => setRenaming(e.target.value)}
              className="max-w-xs"
            />
            <Button type="submit">OK</Button>
            <Button type="button" variant="ghost" onClick={() => setRenaming(null)}>
              Annuler
            </Button>
          </form>
        )}
      </Card>
      {error && <p className="text-sm text-danger">{error}</p>}
      {selected && trees.length > 0 && (
        <>
          <p className="text-xs text-muted">
            Les {acquiredAtLevel(character.level ?? 1)} premiers points sont acquis au niveau{" "}
            {character.level}, les suivants sont projetés (pointillés).
            {canEdit && " Clic gauche : + 1, clic droit : − 1. Enregistré automatiquement."}
          </p>
          <TalentTrees
            trees={trees}
            build={build}
            acquired={acquired}
            readOnly={!canEdit}
            onAdd={(t) => update([...points, t.id])}
            onRemove={(t) => update(removeLast(points, t.id))}
          />
        </>
      )}
      {trees.length === 0 && (
        <Card className="text-sm text-muted">Pas de talents importés pour cette classe.</Card>
      )}
    </div>
  );
}
