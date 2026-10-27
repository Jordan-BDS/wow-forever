import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "@/api/client";
import { unwrap, useGameData } from "@/api/hooks";
import { ClassDot, ClassName } from "@/components/game";
import { Card, Input, PageTitle, Select, Spinner } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { findClass } from "@/lib/game";
import { useWowheadTooltips } from "@/lib/wowhead";

/** Catalogue des recettes importées, avec les crafteurs de la guilde qui les connaissent. */
export function RecipesPage() {
  const gamedata = useGameData();
  const [query, setQuery] = useState("");
  const [profession, setProfession] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const id = window.setTimeout(() => setQ(query.trim()), 250);
    return () => window.clearTimeout(id);
  }, [query]);

  const recipes = useQuery({
    queryKey: ["recipes", "catalogue", q, profession],
    queryFn: () =>
      unwrap(api.GET("/api/recipes/", { params: { query: { q, profession: profession || undefined } } })),
    enabled: q.length >= 2 || profession !== "",
    placeholderData: (previous) => previous,
  });
  useWowheadTooltips([recipes.data]);

  return (
    <>
      <PageTitle>Recettes</PageTitle>
      <Card className="mb-4 flex flex-wrap items-end gap-3">
        <label className="flex-1 text-sm">
          <span className="text-muted">Nom de recette ou d'objet (français ou anglais)</span>
          <Input value={query} onChange={(e) => setQuery(e.target.value)} autoFocus />
        </label>
        <label className="text-sm">
          <span className="text-muted">Métier</span>
          <Select className="block w-full" value={profession} onChange={(e) => setProfession(e.target.value)}>
            <option value="">Tous les métiers</option>
            {gamedata.data?.professions.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.name}
              </option>
            ))}
          </Select>
        </label>
      </Card>
      {!recipes.data && !recipes.isFetching && (
        <p className="text-sm text-muted">
          Tape au moins deux lettres ou choisis un métier. Pour commander un craft, passe par l'onglet
          Métiers.
        </p>
      )}
      {recipes.isFetching && !recipes.data && <Spinner />}
      {recipes.data && (
        <Card className="p-0">
          {recipes.data.length === 0 ? (
            <p className="p-6 text-center text-sm text-muted">Aucune recette.</p>
          ) : (
            <ul className="divide-y divide-border/60 text-sm">
              {recipes.data.map((recipe) => (
                <li key={recipe.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
                  <img
                    src={recipe.icon_url}
                    alt=""
                    className="size-8 rounded border border-border"
                    loading="lazy"
                  />
                  <div className="min-w-0 flex-1">
                    <WowheadLink
                      kind="spell"
                      id={recipe.id}
                      className="font-medium text-text hover:text-gold"
                    >
                      {recipe.name}
                    </WowheadLink>
                    <div className="text-xs text-muted">
                      {gamedata.data?.professions.find((p) => p.slug === recipe.profession)?.name}{" "}
                      {recipe.min_skill}
                      {recipe.product && ` · ${recipe.quantity} × ${recipe.product.name}`}
                      {(recipe.reagents as { name: string; count: number }[]).length > 0 &&
                        ` · ${(recipe.reagents as { name: string; count: number }[]).map((r) => `${r.count} ${r.name}`).join(", ")}`}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs">
                    {recipe.crafters.length === 0 ? (
                      <span className="text-muted">personne ne la connaît</span>
                    ) : (
                      recipe.crafters.map((c) => (
                        <Link
                          key={c.character_id}
                          to={`/personnages/${c.character_id}`}
                          className="flex items-center gap-1 rounded-sm border border-border px-2 py-1 text-text hover:border-gold"
                        >
                          <ClassDot playerClass={findClass(gamedata.data, c.player_class)} />
                          <ClassName playerClass={findClass(gamedata.data, c.player_class)}>
                            {c.name}
                          </ClassName>
                          <span className="text-muted">{c.skill}</span>
                        </Link>
                      ))
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </>
  );
}
