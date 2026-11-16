// Primes posées à la main sur des joueurs ou des guildes adverses : liste, pose, annulation, paiements déclarés, registre des dettes.
import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type BountyUser = { id: number; display_name: string };
export type BountyItem = { id: number; name: string; quality: number; icon_url: string };

/** Ce qu'une prime doit à un chasseur : l'or en cuivre, les objets en nombre. */
export type BountyDue = {
  hunter: BountyUser;
  kills: number;
  amount: number;
  items: number;
  paid: number;
  items_paid: number;
  owed: number;
  items_owed: number;
};

export type BountyKill = {
  at: string;
  zone: string;
  /** Le joueur abattu (pour une prime de guilde, l'un de ses membres). */
  victim: string;
  /** Les chasseurs du kill et la part de chacun. */
  hunters: {
    user: BountyUser;
    character: { id: number; name: string; surname: string; player_class: string };
    amount: number;
    items: number;
  }[];
};

export type Bounty = {
  id: number;
  target: string;
  /** La cible est une guilde adverse : chaque membre abattu compte pour un kill. */
  guild: boolean;
  poster: BountyUser;
  /** Or par kill, en cuivre. */
  amount: number;
  item: BountyItem | null;
  item_count: number;
  max_kills: number;
  note: string;
  created_at: string;
  cancelled_at: string | null;
  /** « done » : tous les kills payés ont été faits. */
  status: "open" | "done" | "cancelled";
  kills: BountyKill[];
  dues: BountyDue[];
  can_cancel: boolean;
  can_pay: boolean;
};

export type LedgerLine = {
  from: BountyUser;
  to: BountyUser;
  amount: number;
  items: (BountyItem & { count: number })[];
};

export type BountyReport = { bounties: Bounty[]; ledger: LedgerLine[] };

export type NewBounty = {
  target: string;
  guild?: boolean;
  /** Pièces d'or par kill. */
  gold: number;
  max_kills: number;
  item_id?: number;
  item_count?: number;
  note?: string;
};

const KEY = ["sync", "bounties"] as const;

export const bountiesQuery = queryOptions({
  queryKey: KEY,
  staleTime: 30_000,
  queryFn: async () => {
    const { data, error } = await api.GET("/api/sync/bounties/");
    if (error || !data) throw error ?? new Error();
    return data as unknown as BountyReport;
  },
});

export function useBounties() {
  return useQuery(bountiesQuery);
}

/** Chaque action renvoie la page entière à jour : elle remplace celle en cache. */
function useBountyAction<T>(run: (input: T) => Promise<{ data?: unknown; error?: unknown }>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: T) => {
      const { data, error } = await run(input);
      if (error || !data) throw error ?? new Error();
      return data as unknown as BountyReport;
    },
    onSuccess: (report) => queryClient.setQueryData(KEY, report),
  });
}

export function usePostBounty() {
  return useBountyAction((body: NewBounty) => api.POST("/api/sync/bounties/", { body }));
}

export function useCancelBounty() {
  return useBountyAction((id: number) =>
    api.POST("/api/sync/bounties/{id}/cancel/", { params: { path: { id } } }),
  );
}

export function usePayBounty() {
  return useBountyAction(({ id, hunterId }: { id: number; hunterId: number }) =>
    api.POST("/api/sync/bounties/{id}/payments/", {
      params: { path: { id } },
      body: { hunter_id: hunterId },
    }),
  );
}

/** Ce qu'une prime offre par kill : « 50 po », « 3 × Étoffe runique », ou les deux. */
export function rewardParts(amount: number, itemCount: number, itemName: string | undefined): string[] {
  const parts = [];
  if (amount > 0) parts.push(`${Math.round(amount / 10000)} po`);
  if (itemCount > 0 && itemName) parts.push(`${itemCount} × ${itemName}`);
  return parts;
}
