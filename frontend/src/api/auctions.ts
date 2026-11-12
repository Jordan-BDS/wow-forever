// Prix de l'hôtel des ventes (GM) : dernier scan comparé à un scan de référence, historique par objet,
// recettes favorites avec le coût de leurs composants.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

/** « sold » et « posted » : enchères parties ou arrivées depuis le scan de référence (estimation). */
export type AuctionSort = "name" | "price" | "listed" | "up" | "down" | "sold" | "posted";
/** Référence de la variation : le scan précédent, ou le dernier scan vieux d'au moins un jour / une semaine. */
export type AuctionSince = "prev" | "day" | "week";

export type AuctionScan = { id: number; house: string; scanned_at: string; items: number };

export type AuctionRow = {
  item_id: number;
  name: string;
  /** Faux si l'objet manque à l'index du site : il est alors nommé par son ID. */
  known: boolean;
  quality: number;
  icon_url: string;
  /** Prix le plus bas à l'unité, en cuivre. */
  price: number;
  listed: number | null;
  previous_price: number | null;
  /** Variation en % depuis le scan de référence, null si l'objet n'y était pas. */
  change: number | null;
  /** Vrai si l'objet était au scan de référence et n'a plus aucune enchère (tris de mouvements seulement). */
  gone: boolean;
  previous_listed: number | null;
  /** Enchères en plus ou en moins depuis le scan de référence, null si l'un des deux nombres manque. */
  listed_change: number | null;
  /** Valeur estimée du mouvement, en cuivre : une unité par enchère, au prix le plus bas. */
  moved: number | null;
};

export type AuctionOverview = {
  houses: { house: string; scans: number; last_scan: string; first_scan: string }[];
  house: string;
  scan: AuctionScan | null;
  baseline: AuctionScan | null;
  since: AuctionSince;
  sort: AuctionSort;
  total: number;
  page: number;
  pages: number;
  results: AuctionRow[];
};

export type AuctionHistory = {
  item_id: number;
  house: string;
  name: string;
  quality: number;
  icon_url: string;
  min: number | null;
  max: number | null;
  average: number | null;
  points: { at: string; price: number; listed: number | null }[];
};

export type AuctionFilters = {
  house: string;
  q: string;
  sort: AuctionSort;
  since: AuctionSince;
  page: number;
};

export function useAuctions(filters: AuctionFilters, enabled: boolean) {
  return useQuery({
    queryKey: ["sync", "auctions", filters] as const,
    enabled,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/sync/auctions/", {
        params: { query: { ...filters, house: filters.house || undefined, q: filters.q || undefined } },
      });
      if (error || !data) throw error ?? new Error();
      return data as unknown as AuctionOverview;
    },
  });
}

export function useAuctionHistory(itemId: number, house: string) {
  return useQuery({
    queryKey: ["sync", "auctions", "item", itemId, house] as const,
    staleTime: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/sync/auctions/items/{item_id}/", {
        params: { path: { item_id: itemId }, query: { house: house || undefined } },
      });
      if (error || !data) throw error ?? new Error();
      return data as unknown as AuctionHistory;
    },
  });
}

/** Un objet d'une recette (produit ou composant) et son prix au dernier scan, null s'il n'est pas en vente. */
export type RecipeItem = {
  item_id: number;
  name: string;
  quality: number;
  icon_url: string;
  price: number | null;
  listed: number | null;
};

export type RecipeCost = {
  recipe_id: number;
  name: string;
  icon_url: string;
  profession: string;
  min_skill: number;
  /** Nombre d'objets produits par fabrication. */
  quantity: number;
  favorite: boolean;
  product: RecipeItem | null;
  reagents: (RecipeItem & { count: number; total: number | null })[];
  /** Coût des composants en vente, null si aucun ne l'est. */
  cost: number | null;
  /** Composants sans prix à l'hôtel des ventes : ils manquent au coût et au bénéfice. */
  missing: number;
  revenue: number | null;
  profit: number | null;
  /** Bénéfice en % du coût. */
  margin: number | null;
};

export type RecipeCosts = {
  house: string;
  scan: AuctionScan | null;
  /** Vrai si `results` répond à la recherche, faux si ce sont les favorites. */
  searching: boolean;
  favorites: number;
  results: RecipeCost[];
};

const RECIPES_KEY = ["sync", "auctions", "recipes"] as const;

/** Les recettes favorites, ou celles que trouve `q` (deux lettres au moins). */
export function useRecipeCosts(house: string, q: string, enabled: boolean) {
  return useQuery({
    queryKey: [...RECIPES_KEY, house, q] as const,
    enabled,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/sync/auctions/recipes/", {
        params: { query: { house: house || undefined, q: q || undefined } },
      });
      if (error || !data) throw error ?? new Error();
      return data as unknown as RecipeCosts;
    },
  });
}

export function useSetFavoriteRecipe() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ recipeId, favorite }: { recipeId: number; favorite: boolean }) => {
      const params = { path: { recipe_id: recipeId } };
      const { error } = favorite
        ? await api.PUT("/api/sync/auctions/recipes/{recipe_id}/", { params })
        : await api.DELETE("/api/sync/auctions/recipes/{recipe_id}/", { params });
      if (error) throw error;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: RECIPES_KEY }),
  });
}

/** 123456 cuivres → « 12 po 34 pa 56 pc » (les parties nulles sont omises). */
export function formatMoney(copper: number): string {
  const total = Math.max(0, Math.round(copper));
  const parts = [
    [Math.floor(total / 10000), "po"],
    [Math.floor(total / 100) % 100, "pa"],
    [total % 100, "pc"],
  ] as const;
  const shown = parts.filter(([value]) => value > 0).map(([value, unit]) => `${value} ${unit}`);
  return shown.length ? shown.join(" ") : "0 pc";
}

/** « +25 % », « −50 % », « = ». */
export function formatChange(change: number): string {
  if (change === 0) return "=";
  const text = Math.abs(change) >= 10 ? Math.abs(change).toFixed(0) : Math.abs(change).toFixed(1);
  return `${change > 0 ? "+" : "−"}${text} %`;
}

/** Graduations « rondes » couvrant [min, max] : pas de 1, 2 ou 5 × 10ⁿ, `count` intervalles environ. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!(max > min)) {
    // Série plate : une marge autour de la valeur, pour que la ligne ne colle pas à un bord.
    const pad = Math.max(1, Math.abs(min) * 0.1);
    return niceTicks(Math.max(0, min - pad), min + pad, count);
  }
  const raw = (max - min) / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = Math.max(1, ([1, 2, 5, 10].find((m) => m * power >= raw) ?? 10) * power);
  const ticks = [];
  for (let tick = Math.floor(min / step) * step; tick < max + step; tick += step) ticks.push(tick);
  return ticks;
}
