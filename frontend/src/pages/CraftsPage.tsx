import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, errorMessage, fieldErrors, type CraftRequest, type RecipeIndex } from "@/api/client";
import { unwrap, useCharacters, useGameData, useInvalidate } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { ClassDot, ClassName } from "@/components/game";
import { Button, Card, Field, Input, PageTitle, Select, Spinner } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { formatDateTime } from "@/lib/game";
import { isOfficerOrAbove } from "@/lib/roles";
import { findClass } from "@/lib/game";
import { useWowheadTooltips } from "@/lib/wowhead";

type Scope = "open" | "mine" | "doable" | "all";
const SCOPES: { value: Scope; label: string }[] = [
  { value: "open", label: "Ouvertes" },
  { value: "doable", label: "Je peux les faire" },
  { value: "mine", label: "Mes demandes" },
  { value: "all", label: "Toutes" },
];
const STATUS_LABEL: Record<CraftRequest["status"], string> = {
  open: "Ouverte",
  taken: "Prise en charge",
  delivered: "Livrée",
  cancelled: "Annulée",
};
const MATERIALS_LABEL = {
  none: "Aucun composant fourni",
  partial: "Composants partiels",
  all: "Tous les composants fournis",
};

function useDebounced(value: string, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export function CraftsPage() {
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const q = useDebounced(query.trim());
  const [scope, setScope] = useState<Scope>("open");
  const [creating, setCreating] = useState(false);
  const gamedata = useGameData();
  const highlighted = Number(params.get("demande") ?? 0);

  const crafters = useQuery({
    queryKey: ["recipes", "crafters", q],
    queryFn: () => unwrap(api.GET("/api/recipes/", { params: { query: { q, known: true } } })),
    enabled: q.length >= 2,
    placeholderData: (previous) => previous,
  });
  const requests = useQuery({
    queryKey: ["craft-requests", scope],
    queryFn: () => unwrap(api.GET("/api/craft-requests/", { params: { query: { scope } } })),
  });
  useWowheadTooltips([crafters.data, requests.data]);

  return (
    <>
      <PageTitle
        actions={
          <Button variant={creating ? "ghost" : "primary"} onClick={() => setCreating((v) => !v)}>
            {creating ? "Annuler" : "Nouvelle demande"}
          </Button>
        }
      >
        Crafts
      </PageTitle>

      {creating && (
        <RequestForm
          onDone={() => {
            setCreating(false);
            setScope("mine");
          }}
        />
      )}

      <section className="mb-6">
        <h2 className="mb-2 text-sm text-muted">Qui sait crafter ?</h2>
        <Card className="space-y-3">
          <Input
            value={query}
            placeholder="Nom de recette ou d'objet (FR ou EN)…"
            onChange={(e) => setQuery(e.target.value)}
          />
          {q.length < 2 ? (
            <p className="text-xs text-muted">
              Tape au moins deux lettres. Seules les recettes connues par au moins un perso de la guilde
              apparaissent.
            </p>
          ) : crafters.isPending ? (
            <Spinner />
          ) : crafters.data?.length === 0 ? (
            <p className="text-sm text-muted">Personne ne connaît de recette correspondant à « {q} ».</p>
          ) : (
            <ul className="divide-y divide-border/60 text-sm">
              {crafters.data?.map((recipe) => (
                <li key={recipe.id} className="flex flex-wrap items-center gap-3 py-2">
                  <img src={recipe.icon_url} alt="" className="size-8 rounded border border-border" />
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
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs">
                    {recipe.crafters.map((c) => (
                      <Link
                        key={c.character_id}
                        to={`/personnages/${c.character_id}`}
                        className="flex items-center gap-1 rounded border border-border px-2 py-1 text-text hover:border-gold"
                      >
                        <ClassDot playerClass={findClass(gamedata.data, c.player_class)} />
                        <ClassName playerClass={findClass(gamedata.data, c.player_class)}>{c.name}</ClassName>
                        <span className="text-muted">
                          {c.owner_name} · {c.skill}
                        </span>
                      </Link>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      <section>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h2 className="text-sm text-muted">Demandes</h2>
          <div className="ml-auto flex rounded-md border border-border text-xs">
            {SCOPES.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => setScope(s.value)}
                className={clsx(
                  "px-3 py-1.5",
                  scope === s.value ? "bg-surface-2 text-text" : "text-muted hover:text-text",
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        {requests.isPending ? (
          <Spinner />
        ) : requests.data?.length === 0 ? (
          <Card className="text-sm text-muted">Aucune demande ici.</Card>
        ) : (
          <div className="space-y-2">
            {requests.data?.map((craft) => (
              <RequestCard key={craft.id} craft={craft} highlighted={craft.id === highlighted} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function RequestCard({ craft, highlighted }: { craft: CraftRequest; highlighted: boolean }) {
  const me = useCurrentUser();
  const invalidate = useInvalidate();
  const characters = useCharacters();
  const gamedata = useGameData();
  const [error, setError] = useState<string | null>(null);
  const mine = (characters.data ?? []).filter((c) => c.owner.id === me.id);
  const eligible = mine.filter((c) => craft.recipe.crafters.some((k) => k.character_id === c.id));
  const [characterId, setCharacterId] = useState<number>(eligible[0]?.id ?? 0);
  const isRequester = craft.requester.id === me.id;
  const isCrafter = craft.crafter?.owner.id === me.id;
  const officer = isOfficerOrAbove(me.site_role);

  const act = useMutation({
    mutationFn: async (kind: "take" | "deliver" | "release" | "cancel") => {
      const base = { params: { path: { id: craft.id } } };
      let error: unknown;
      if (kind === "take") {
        ({ error } = await api.POST("/api/craft-requests/{id}/take/", {
          ...base,
          body: { character: characterId },
        }));
      } else if (kind === "deliver") {
        ({ error } = await api.POST("/api/craft-requests/{id}/deliver/", base));
      } else if (kind === "release") {
        ({ error } = await api.POST("/api/craft-requests/{id}/release/", base));
      } else {
        ({ error } = await api.POST("/api/craft-requests/{id}/cancel/", base));
      }
      if (error) throw error;
    },
    onSuccess: () => {
      setError(null);
      return invalidate(["craft-requests"]);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const canTake =
    craft.status === "open" &&
    eligible.length > 0 &&
    !isRequester &&
    (!craft.target_character || eligible.some((c) => c.id === craft.target_character?.id) || officer);

  return (
    <Card
      className={clsx(
        "flex flex-wrap items-center gap-3 text-sm",
        highlighted && "border-gold/60",
        !["open", "taken"].includes(craft.status) && "opacity-60",
      )}
    >
      <img src={craft.recipe.icon_url} alt="" className="size-9 rounded border border-border" />
      <div className="min-w-0 flex-1">
        <div className="font-medium">
          {craft.quantity} ×{" "}
          <WowheadLink kind="spell" id={craft.recipe.id} className="text-text hover:text-gold">
            {craft.recipe.name}
          </WowheadLink>
          <span className="ml-2 rounded-sm border border-gold/50 px-1.5 py-0.5 text-xs text-gold">
            {gamedata.data?.professions.find((p) => p.slug === craft.recipe.profession)?.name ??
              craft.recipe.profession}{" "}
            {craft.recipe.min_skill}
          </span>
          <span
            className={clsx(
              "ml-2 rounded border px-1.5 py-0.5 text-xs",
              craft.status === "open"
                ? "border-gold/50 text-gold"
                : craft.status === "taken"
                  ? "border-alliance/50 text-alliance"
                  : "border-border text-muted",
            )}
          >
            {STATUS_LABEL[craft.status]}
          </span>
        </div>
        <div className="text-xs text-muted">
          Pour <Link to={`/membres/${craft.requester.id}`}>{craft.requester.display_name}</Link> ·{" "}
          {formatDateTime(craft.created_at)} · {MATERIALS_LABEL[craft.materials ?? "none"]}
          {craft.target_character && (
            <>
              {" "}
              · cible{" "}
              <ClassName playerClass={findClass(gamedata.data, craft.target_character.player_class)}>
                {craft.target_character.name}
              </ClassName>
            </>
          )}
          {craft.crafter && (
            <>
              {" "}
              · par{" "}
              <ClassName playerClass={findClass(gamedata.data, craft.crafter.player_class)}>
                {craft.crafter.name}
              </ClassName>{" "}
              ({craft.crafter.owner.display_name})
            </>
          )}
          {craft.note && <span className="block">« {craft.note} »</span>}
        </div>
        {error && <p className="text-xs text-danger">{error}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {canTake && (
          <>
            {eligible.length > 1 && (
              <Select value={characterId} onChange={(e) => setCharacterId(Number(e.target.value))}>
                {eligible.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            )}
            <Button disabled={act.isPending} onClick={() => act.mutate("take")}>
              Je m'en occupe
            </Button>
          </>
        )}
        {craft.status === "taken" && (isCrafter || isRequester || officer) && (
          <Button disabled={act.isPending} onClick={() => act.mutate("deliver")}>
            Livrée
          </Button>
        )}
        {craft.status === "taken" && (isCrafter || officer) && (
          <Button variant="ghost" disabled={act.isPending} onClick={() => act.mutate("release")}>
            Rendre
          </Button>
        )}
        {["open", "taken"].includes(craft.status) && (isRequester || officer) && (
          <Button variant="danger" disabled={act.isPending} onClick={() => act.mutate("cancel")}>
            Annuler
          </Button>
        )}
      </div>
    </Card>
  );
}

function RequestForm({ onDone }: { onDone: () => void }) {
  const invalidate = useInvalidate();
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim());
  const [recipe, setRecipe] = useState<RecipeIndex | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [materials, setMaterials] = useState<"none" | "partial" | "all">("none");
  const [target, setTarget] = useState<number | "">("");
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const gamedata = useGameData();

  const results = useQuery({
    queryKey: ["recipes", "search", q],
    queryFn: () => unwrap(api.GET("/api/recipes/", { params: { query: { q } } })),
    enabled: q.length >= 2 && !recipe,
  });

  const create = useMutation({
    mutationFn: async () => {
      if (!recipe) throw { detail: "Choisis une recette." };
      const { error } = await api.POST("/api/craft-requests/", {
        body: {
          recipe_id: recipe.id,
          quantity,
          materials,
          note,
          target_character_id: target === "" ? null : target,
        },
      });
      if (error) throw error;
    },
    onSuccess: async () => {
      await invalidate(["craft-requests"]);
      onDone();
    },
    onError: (e) => setErrors(fieldErrors(e)),
  });

  return (
    <Card className="mb-6 space-y-3">
      <h3 className="font-display text-lg">Nouvelle demande de craft</h3>
      {recipe ? (
        <div className="flex items-center gap-3 text-sm">
          <img src={recipe.icon_url} alt="" className="size-8 rounded border border-border" />
          <span className="font-medium">{recipe.name}</span>
          <span className="text-muted">
            {gamedata.data?.professions.find((p) => p.slug === recipe.profession)?.name} {recipe.min_skill} ·{" "}
            {recipe.crafters.length} crafteur{recipe.crafters.length > 1 && "s"} dans la guilde
          </span>
          <Button variant="ghost" onClick={() => setRecipe(null)}>
            Changer
          </Button>
        </div>
      ) : (
        <Field label="Recette (nom de recette ou d'objet)">
          <Input value={query} autoFocus onChange={(e) => setQuery(e.target.value)} />
          {results.data && results.data.length > 0 && (
            <ul className="mt-1 max-h-60 divide-y divide-border/60 overflow-y-auto rounded-md border border-border bg-bg text-sm">
              {results.data.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => setRecipe(r)}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-surface-2"
                  >
                    <img src={r.icon_url} alt="" className="size-6 rounded" loading="lazy" />
                    <span className="flex-1 truncate">{r.name}</span>
                    <span className="text-xs text-muted">
                      {r.crafters.length ? `${r.crafters.length} crafteur(s)` : "personne ne la connaît"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {errors.recipe_id && <p className="text-xs text-danger">{errors.recipe_id}</p>}
        </Field>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Quantité">
          <Input
            type="number"
            min={1}
            max={200}
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value))}
          />
        </Field>
        <Field label="Composants">
          <Select
            className="w-full"
            value={materials}
            onChange={(e) => setMaterials(e.target.value as typeof materials)}
          >
            {(Object.keys(MATERIALS_LABEL) as (keyof typeof MATERIALS_LABEL)[]).map((k) => (
              <option key={k} value={k}>
                {MATERIALS_LABEL[k]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Crafteur ciblé (facultatif)">
          <Select
            className="w-full"
            value={target}
            disabled={!recipe}
            onChange={(e) => setTarget(e.target.value === "" ? "" : Number(e.target.value))}
          >
            <option value="">Ouvert à tous</option>
            {recipe?.crafters.map((c) => (
              <option key={c.character_id} value={c.character_id}>
                {c.name} ({c.owner_name}, {c.skill})
              </option>
            ))}
          </Select>
          {errors.target_character_id && <p className="text-xs text-danger">{errors.target_character_id}</p>}
        </Field>
      </div>
      <Field label="Note (pourboire, urgence…)">
        <Input value={note} maxLength={240} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <div className="flex items-center gap-3">
        <Button disabled={!recipe || create.isPending} onClick={() => create.mutate()}>
          Envoyer la demande
        </Button>
        {errors.detail && <span className="text-sm text-danger">{errors.detail}</span>}
      </div>
    </Card>
  );
}
