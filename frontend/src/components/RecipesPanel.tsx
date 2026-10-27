import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, errorMessage, type Character, type RecipeIndex } from "@/api/client";
import { unwrap, useGameData, useInvalidate } from "@/api/hooks";
import { Button, Card, Input, Spinner } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { useWowheadTooltips } from "@/lib/wowhead";

interface Props {
  character: Character;
  canEdit: boolean;
}

const KEY = (id: number) => ["characters", id, "recipes"] as const;

/** Catalogue des recettes des métiers du personnage, à cocher. */
export function RecipesPanel({ character, canEdit }: Props) {
  const gamedata = useGameData();
  const invalidate = useInvalidate();
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const professions = (character.professions ?? []).map((p) => p.profession);

  const known = useQuery({
    queryKey: KEY(character.id),
    queryFn: () =>
      unwrap(api.GET("/api/characters/{id}/recipes/", { params: { path: { id: character.id } } })),
  });
  const catalog = useQuery({
    queryKey: ["recipes", "catalog", professions.join(",")],
    queryFn: async () => {
      const lists = await Promise.all(
        professions.map((slug) =>
          unwrap(api.GET("/api/recipes/", { params: { query: { profession: slug } } })),
        ),
      );
      return lists.flat();
    },
    staleTime: Infinity,
    enabled: professions.length > 0,
  });
  useWowheadTooltips([catalog.data, query]);

  const save = useMutation({
    mutationFn: async (recipes: number[]) => {
      const { error } = await api.PUT("/api/characters/{id}/recipes/", {
        params: { path: { id: character.id } },
        body: { recipes },
      });
      if (error) throw error;
    },
    onSuccess: () => {
      setError(null);
      return invalidate(KEY(character.id), ["recipes"]);
    },
    onError: (e) => setError(errorMessage(e)),
  });
  const auto = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/characters/{id}/recipes/", {
        params: { path: { id: character.id } },
      });
      if (error || !data) throw error ?? new Error();
      return data as { recipes: number[]; added?: number };
    },
    onSuccess: (data) => {
      setError(data.added ? null : "Rien de nouveau à cocher.");
      return invalidate(KEY(character.id), ["recipes"]);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const knownSet = useMemo(() => new Set(known.data?.recipes ?? []), [known.data]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (catalog.data ?? []).filter(
      (r) =>
        !q ||
        r.name.toLowerCase().includes(q) ||
        r.product?.name.toLowerCase().includes(q) ||
        r.product?.name_en?.toLowerCase().includes(q),
    );
  }, [catalog.data, query]);

  if (professions.length === 0) {
    return (
      <Card className="text-sm text-muted">
        Renseigne d'abord les métiers du personnage (bouton Modifier).
      </Card>
    );
  }
  if (known.isPending || catalog.isPending) return <Spinner />;

  const toggle = (recipe: RecipeIndex) => {
    const next = new Set(knownSet);
    if (next.has(recipe.id)) next.delete(recipe.id);
    else next.add(recipe.id);
    save.mutate([...next]);
  };

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-3 text-sm">
        <Input
          value={query}
          placeholder="Filtrer les recettes…"
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-xs"
        />
        <span className="text-muted">
          {knownSet.size} recette{knownSet.size > 1 && "s"} connue{knownSet.size > 1 && "s"} sur{" "}
          {catalog.data?.length}
        </span>
        {canEdit && (
          <Button variant="ghost" disabled={auto.isPending} onClick={() => auto.mutate()} className="ml-auto">
            Cocher toutes les recettes jusqu'à mon niveau
          </Button>
        )}
        {error && <span className="w-full text-danger">{error}</span>}
      </Card>
      {professions.map((slug) => {
        const profession = gamedata.data?.professions.find((p) => p.slug === slug);
        const rows = filtered
          .filter((r) => r.profession === slug)
          .sort((a, b) => (a.min_skill ?? 0) - (b.min_skill ?? 0));
        return (
          <Card key={slug} className="p-0">
            <h3 className="border-b border-border px-3 py-2 font-display text-lg">
              {profession?.name ?? slug}
              <span className="ml-2 text-xs text-muted">
                {rows.filter((r) => knownSet.has(r.id)).length}/{rows.length}
              </span>
            </h3>
            {rows.length === 0 ? (
              <p className="p-4 text-sm text-muted">Aucune recette{query && " pour ce filtre"}.</p>
            ) : (
              <ul className="max-h-[32rem] divide-y divide-border/60 overflow-y-auto text-sm">
                {rows.map((recipe) => (
                  <li key={recipe.id}>
                    <label
                      className={
                        canEdit
                          ? "flex cursor-pointer items-center gap-3 px-3 py-1.5 hover:bg-surface-2"
                          : "flex items-center gap-3 px-3 py-1.5"
                      }
                    >
                      <input
                        type="checkbox"
                        checked={knownSet.has(recipe.id)}
                        disabled={!canEdit || save.isPending}
                        onChange={() => toggle(recipe)}
                        className="accent-gold"
                      />
                      <img
                        src={recipe.icon_url}
                        alt=""
                        className="size-7 rounded border border-border"
                        loading="lazy"
                      />
                      <span className="min-w-0 flex-1 truncate">
                        <WowheadLink kind="spell" id={recipe.id} className="text-text hover:text-gold">
                          {recipe.name}
                        </WowheadLink>
                        <span className="ml-2 text-xs text-muted">
                          {recipe.source}
                          {recipe.is_forever && " · Forever"}
                        </span>
                      </span>
                      <span className="font-mono text-xs text-muted">{recipe.min_skill}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        );
      })}
    </div>
  );
}
