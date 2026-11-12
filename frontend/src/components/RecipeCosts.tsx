import { useState } from "react";
import clsx from "clsx";
import { formatMoney, useRecipeCosts, useSetFavoriteRecipe, type RecipeCost } from "@/api/auctions";
import { ItemPriceHistory } from "@/components/PriceChart";
import { Card, Input, Pill, Spinner } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { formatDateTime } from "@/lib/game";
import { useDebounced } from "@/lib/useDebounced";
import { useWowheadTooltips } from "@/lib/wowhead";

type Sort = "name" | "profit";

const SORTS: { value: Sort; label: string }[] = [
  { value: "name", label: "Nom" },
  { value: "profit", label: "Bénéfice" },
];

/** « +1 po 50 pa », « −20 pa ». */
function formatSigned(copper: number): string {
  return `${copper < 0 ? "−" : "+"}${formatMoney(Math.abs(copper))}`;
}

function sorted(recipes: RecipeCost[], sort: Sort): RecipeCost[] {
  if (sort === "name") return recipes; // l'ordre du site
  // Les recettes sans bénéfice calculable passent après les autres.
  return [...recipes].sort((a, b) => (b.profit ?? -Infinity) - (a.profit ?? -Infinity));
}

/** Onglet « Recettes favorites » : les recettes suivies, ce que coûtent leurs composants à l'hôtel des
 * ventes et ce que rapporte leur produit ; la recherche sert à en suivre d'autres. */
export function RecipeCosts({ house }: { house: string }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("name");
  const [open, setOpen] = useState<number | null>(null);
  const q = useDebounced(query.trim());
  const recipes = useRecipeCosts(house, q.length >= 2 ? q : "", true);
  const setFavorite = useSetFavoriteRecipe();
  useWowheadTooltips([recipes.data, open]);

  if (recipes.isError) return <p className="text-sm text-danger">Impossible de charger les recettes.</p>;
  if (!recipes.data) return <Spinner />;
  const data = recipes.data;
  const rows = data.searching ? data.results : sorted(data.results, sort);

  return (
    <>
      <Card className="mb-4 space-y-3">
        <label className="block text-sm">
          <span className="text-muted">Chercher une recette à suivre (nom de recette ou d'objet)</span>
          <Input
            value={query}
            placeholder="Ex. Rouleau d'étoffe de lin"
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(null);
            }}
          />
        </label>
        {!data.searching && data.results.length > 1 && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted">Trier par</span>
            {SORTS.map((s) => (
              <Pill key={s.value} active={sort === s.value} onClick={() => setSort(s.value)}>
                {s.label}
              </Pill>
            ))}
          </div>
        )}
        <p className="text-xs text-muted">
          {data.scan
            ? `${data.house} · prix du scan du ${formatDateTime(data.scan.scanned_at)}`
            : "Aucun scan : pas encore de prix"}{" "}
          · {data.favorites} recette{data.favorites > 1 ? "s" : ""} suivie{data.favorites > 1 ? "s" : ""} · le
          coût ne compte que les composants en vente (pas ceux des marchands)
        </p>
      </Card>

      <Card className="p-0">
        {rows.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted">
            {data.searching
              ? "Aucune recette ne correspond."
              : "Aucune recette suivie : cherche une recette ci-dessus et clique sur son étoile."}
          </p>
        ) : (
          <ul className="divide-y divide-border/60">
            {rows.map((recipe) => (
              <RecipeRow
                key={recipe.recipe_id}
                recipe={recipe}
                house={data.house}
                open={open === recipe.recipe_id}
                onToggle={() => setOpen(open === recipe.recipe_id ? null : recipe.recipe_id)}
                busy={setFavorite.isPending}
                onFavorite={() =>
                  setFavorite.mutate({ recipeId: recipe.recipe_id, favorite: !recipe.favorite })
                }
              />
            ))}
          </ul>
        )}
      </Card>
      {setFavorite.isError && <p className="mt-2 text-sm text-danger">Le favori n'a pas pu être changé.</p>}
    </>
  );
}

function Amount({ label, children, note }: { label: string; children: React.ReactNode; note?: string }) {
  return (
    <div className="w-36 text-right">
      <div className="text-xs text-muted">{label}</div>
      <div className="font-mono">{children}</div>
      {note && <div className="text-xs text-muted">{note}</div>}
    </div>
  );
}

function RecipeRow({
  recipe,
  house,
  open,
  onToggle,
  busy,
  onFavorite,
}: {
  recipe: RecipeCost;
  house: string;
  open: boolean;
  onToggle: () => void;
  busy: boolean;
  onFavorite: () => void;
}) {
  const { product, profit } = recipe;
  return (
    <li className="text-sm">
      <div className="flex flex-wrap items-center gap-3 px-3 py-2">
        <button
          type="button"
          onClick={onFavorite}
          disabled={busy}
          aria-pressed={recipe.favorite}
          title={recipe.favorite ? "Ne plus suivre" : "Suivre cette recette"}
          className={clsx(
            "text-xl leading-none transition-colors disabled:opacity-50",
            recipe.favorite ? "text-gold hover:text-gold-light" : "text-muted hover:text-gold",
          )}
        >
          {recipe.favorite ? "★" : "☆"}
        </button>
        {recipe.icon_url ? (
          <img src={recipe.icon_url} alt="" className="size-9 rounded border border-border" loading="lazy" />
        ) : (
          <div className="size-9 rounded border border-border bg-bg" />
        )}
        <div className="min-w-40 flex-1">
          <WowheadLink kind="spell" id={recipe.recipe_id} className="font-medium text-text hover:text-gold">
            {recipe.name}
          </WowheadLink>
          <div className="text-xs text-muted">
            {recipe.profession} {recipe.min_skill}
            {product && ` · ${recipe.quantity} × ${product.name}`}
          </div>
        </div>
        <Amount
          label="Composants"
          note={
            recipe.missing > 0
              ? `${recipe.missing} sans prix`
              : recipe.reagents.length === 0
                ? "aucun composant"
                : undefined
          }
        >
          {recipe.cost != null ? formatMoney(recipe.cost) : "?"}
        </Amount>
        <Amount
          label="Vente"
          note={!product ? "pas d'objet produit" : product.price == null ? "pas en vente" : undefined}
        >
          {recipe.revenue != null ? formatMoney(recipe.revenue) : "?"}
        </Amount>
        <Amount
          label="Bénéfice"
          note={
            recipe.margin != null
              ? `${recipe.margin > 0 ? "+" : ""}${recipe.margin.toFixed(0)} % du coût`
              : undefined
          }
        >
          <span className={profit == null ? undefined : profit >= 0 ? "text-success" : "text-danger"}>
            {profit != null ? formatSigned(profit) : "?"}
          </span>
        </Amount>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="rounded-sm border border-border px-2 py-1 text-xs text-muted hover:border-gold hover:text-gold"
        >
          {open ? "Fermer" : "Détail"}
        </button>
      </div>
      {open && (
        <div className="space-y-4 px-3 pb-4">
          {recipe.reagents.length > 0 && (
            <div className="overflow-x-auto rounded-sm border border-border/60">
              <table className="w-full text-left text-xs">
                <thead className="text-muted">
                  <tr>
                    <th className="px-2 py-1 font-normal">Composant</th>
                    <th className="px-2 py-1 text-right font-normal">Prix à l'unité</th>
                    <th className="px-2 py-1 text-right font-normal">Total</th>
                    <th className="px-2 py-1 text-right font-normal">Enchères</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {recipe.reagents.map((reagent) => (
                    <tr key={reagent.item_id}>
                      <td className="px-2 py-1">
                        <span className="text-muted">{reagent.count} × </span>
                        <WowheadLink
                          kind="item"
                          id={reagent.item_id}
                          quality={reagent.quality}
                          className="hover:underline"
                        >
                          {reagent.name}
                        </WowheadLink>
                      </td>
                      <td className="px-2 py-1 text-right font-mono">
                        {reagent.price != null ? formatMoney(reagent.price) : "pas en vente"}
                      </td>
                      <td className="px-2 py-1 text-right font-mono">
                        {reagent.total != null ? formatMoney(reagent.total) : "?"}
                      </td>
                      <td className="px-2 py-1 text-right">
                        {reagent.listed ?? (reagent.price != null ? "?" : "")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {product && (
            <div className="space-y-2">
              <div className="text-xs text-muted">
                Prix de{" "}
                <WowheadLink
                  kind="item"
                  id={product.item_id}
                  quality={product.quality}
                  className="hover:underline"
                >
                  {product.name}
                </WowheadLink>
              </div>
              <ItemPriceHistory itemId={product.item_id} house={house} />
            </div>
          )}
        </div>
      )}
    </li>
  );
}
