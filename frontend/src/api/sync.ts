// Fiche vivante et classements : les réponses sont des objets libres côté OpenAPI, typés ici à la main.
import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type Tile = { total: number; week: number };

export type CharacterProgress = {
  available: boolean;
  synced_at?: string;
  counting_since?: string | null;
  played?: number | null;
  tiles?: Record<
    | "boss_kills"
    | "dungeons_done"
    | "raids_done"
    | "deaths"
    | "bg_played"
    | "bg_won"
    | "quests"
    | "crafted_total"
    | "hk",
    Tile
  >;
  gathering?: Record<"mining" | "herbalism" | "skinning" | "fishing", number>;
  gathering_week?: Record<"mining" | "herbalism" | "skinning" | "fishing", number>;
  pvp?: {
    hk_lifetime: number | null;
    rank: number | null;
    battlegrounds: { map: string; played: number; won: number }[];
  };
  attunements?: Record<string, boolean>;
  lockouts?: { name: string; reset_at: string | null; raid: boolean; killed: number; bosses: number }[];
  reputations?: { id: number | null; name: string; value: number; reaction: number | null }[];
  bosses?: { id: number | null; name: string; kills: number; first: string | null; last: string | null }[];
  gear?: {
    slot: string;
    item_id: number;
    enchant_id: number | null;
    name: string | null;
    quality: number | null;
    icon: string | null;
    item_level: number | null;
  }[];
  spec_tab?: number | null;
  levels?: { at: string; level: number }[];
  series?: {
    day: string;
    deaths: number;
    boss_kills: number;
    bg_played: number;
    mining: number;
    herbalism: number;
    skinning: number;
    fishing: number;
    quests: number;
  }[];
  syncs?: { received_at: string; source: string; device: string | null }[];
};

export type RankingPeriod = "week" | "month" | "season" | "all";
export type RankingBy = "player" | "character";

export type RankingEntry = {
  rank: number;
  user: { id: number; display_name: string };
  character: { id: number; name: string; player_class: string } | null;
  value: number;
  previous_rank: number | null;
  since: string | null;
};

export type RankingCategory = {
  key: string;
  label: string;
  group: "pve" | "pvp" | "gathering" | "crafting" | "guild" | "optin";
  unit: string;
  shame: boolean;
  note: string;
  total: number;
  entries: RankingEntry[];
  all_entries: { rank: number; user_id: number; value: number }[];
};

export type WeeklyTitle = {
  key: string;
  label: string;
  week_start: string;
  value: number;
  user: { id: number; display_name: string };
  character: { id: number; name: string; player_class: string } | null;
};

export type ProgressionBoss = {
  id: number;
  name: string;
  order: number;
  kills: number;
  first_kill: string | null;
  last_kill: string | null;
  best_group: number;
};

export type Rankings = {
  period: RankingPeriod;
  by: RankingBy;
  start: string | null;
  end: string;
  players: number;
  characters: number;
  categories: RankingCategory[];
  titles: WeeklyTitle[];
  progression: {
    slug: string;
    name: string;
    killed: number;
    total: number;
    first_clear: string | null;
    bosses: ProgressionBoss[];
  }[];
  levels: { label: string; count: number }[];
  week_totals: Record<string, number>;
};

export function useCharacterProgress(characterId: number) {
  return useQuery({
    queryKey: ["sync", "progress", characterId] as const,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/sync/characters/{id}/progress/", {
        params: { path: { id: characterId } },
      });
      if (error || !data) throw error ?? new Error();
      return data as unknown as CharacterProgress;
    },
  });
}

export function useRankings(period: RankingPeriod, by: RankingBy) {
  return useQuery({
    queryKey: ["sync", "rankings", period, by] as const,
    staleTime: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/sync/rankings/", { params: { query: { period, by } } });
      if (error || !data) throw error ?? new Error();
      return data as unknown as Rankings;
    },
  });
}

/** « ▲ 2 », « ▼ 1 », « = », « nouveau ». */
export function rankDelta(entry: RankingEntry): { text: string; tone: "up" | "down" | "same" | "new" } {
  if (entry.previous_rank == null) return { text: "nouveau", tone: "new" };
  const diff = entry.previous_rank - entry.rank;
  if (diff > 0) return { text: `▲ ${diff}`, tone: "up" };
  if (diff < 0) return { text: `▼ ${-diff}`, tone: "down" };
  return { text: "=", tone: "same" };
}

export function formatValue(category: Pick<RankingCategory, "unit">, value: number): string {
  const text = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return category.unit ? `${text} ${category.unit}` : text;
}
