// Prix de l'hôtel des ventes (GM) : dernier scan comparé à un scan de référence, et historique par objet.
import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type AuctionSort = "name" | "price" | "listed" | "up" | "down";
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
