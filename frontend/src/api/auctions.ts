// Prix de l'hôtel des ventes (tous les membres) : dernier scan comparé à un scan de référence, historique par objet,
// objets favoris.
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
  /** Vrai si le joueur suit cet objet. */
  favorite: boolean;
};

/** Un type d'objet, rangé comme dans l'hôtel des ventes du jeu : catégorie, sous-catégorie, emplacement. */
export type AuctionCategory = { key: string; label: string; children: AuctionCategory[] };

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
  categories: AuctionCategory[];
  /** Clé du type d'objet retenu, vide si aucun. */
  category: string;
  /** Nombre d'objets que le joueur suit. */
  favorites: number;
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
  /** Clé d'un type d'objet, vide pour tous. */
  category: string;
  /** Seulement les objets suivis, ceux sans enchère compris. */
  favorites: boolean;
};

export function useAuctions(filters: AuctionFilters, enabled: boolean) {
  return useQuery({
    queryKey: ["sync", "auctions", filters] as const,
    enabled,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/sync/auctions/", {
        params: {
          query: {
            ...filters,
            house: filters.house || undefined,
            q: filters.q || undefined,
            category: filters.category || undefined,
            favorites: filters.favorites || undefined,
          },
        },
      });
      if (error || !data) throw error ?? new Error();
      return data as unknown as AuctionOverview;
    },
  });
}

/** Ce qu'un compagnon a fait d'un fichier de scan (Auctionator, NaowhForever) : le constat le plus récent d'abord. */
export type AuctionReport = {
  id: number;
  /** Dernière fois que le compagnon a fait ce constat, et première. */
  at: string;
  first_at: string;
  count: number;
  user: string;
  device: string | null;
  /** Version du compagnon. */
  companion: string;
  /** L'addon lu. */
  source: string;
  house: string;
  kind:
    | "sent"
    | "duplicate"
    | "unchanged"
    | "failed"
    | "unreadable"
    | "no_scan"
    | "stale"
    | "no_file"
    | "not_allowed";
  detail: string;
  /** Jour du scan compté par Auctionator, depuis le 1er janvier 2020. */
  day: number | null;
  items: number | null;
  scanned_at: string | null;
  file_at: string | null;
};

/** GM : les constats des compagnons sur leurs fichiers de scan, relus toutes les 30 secondes. */
export function useAuctionReports() {
  return useQuery({
    queryKey: ["sync", "auctions", "reports"] as const,
    staleTime: 15_000,
    refetchInterval: 30_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/sync/auctions/reports/");
      if (error || !data) throw error ?? new Error();
      return (data as unknown as { reports: AuctionReport[] }).reports;
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

/** Suit ou ne suit plus un objet : la liste est relue, l'étoile et le filtre « Mes favoris » suivent. */
export function useSetFavoriteItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ itemId, favorite }: { itemId: number; favorite: boolean }) => {
      const params = { path: { item_id: itemId } };
      const { error } = favorite
        ? await api.PUT("/api/sync/auctions/favorites/{item_id}/", { params })
        : await api.DELETE("/api/sync/auctions/favorites/{item_id}/", { params });
      if (error) throw error;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sync", "auctions"] }),
  });
}

/** Les catégories qui mènent à `key`, de la plus large à la plus précise. Vide si la clé n'en nomme aucune. */
export function categoryPath(categories: AuctionCategory[], key: string): AuctionCategory[] {
  for (const category of categories) {
    if (category.key === key) return [category];
    const below = categoryPath(category.children, key);
    if (below.length) return [category, ...below];
  }
  return [];
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
