import { queryOptions, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export const KEYS = {
  gamedata: ["gamedata"] as const,
  characters: ["characters"] as const,
  members: ["members"] as const,
  polls: ["polls"] as const,
  poll: (id: number) => ["polls", id] as const,
  events: ["events"] as const,
  eventsWindow: (from: string, to: string) => ["events", "window", from, to] as const,
  event: (id: number) => ["events", id] as const,
  equipmentSets: (characterId: number) => ["characters", characterId, "equipment-sets"] as const,
  talentBuilds: (characterId: number) => ["characters", characterId, "talent-builds"] as const,
  classTalents: (slug: string) => ["talents", slug] as const,
  guildAvailability: ["availability", "guild"] as const,
  myAvailability: ["availability", "me"] as const,
  syncPending: ["sync", "pending"] as const,
  syncDevices: ["sync", "devices"] as const,
  syncImports: ["sync", "imports"] as const,
  syncRelease: ["sync", "release"] as const,
};

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error || data === undefined) throw error ?? new Error(`Erreur ${response.status}`);
  return data;
}

/** La requête des données de jeu : partagée par `useGameData` et le préchargement du démarrage. */
export const gameDataQuery = queryOptions({
  queryKey: KEYS.gamedata,
  queryFn: () => unwrap(api.GET("/api/gamedata/")),
  staleTime: Infinity,
});

export function useGameData() {
  return useQuery(gameDataQuery);
}

// Les requêtes sans paramètre sont des objets partagés : le hook de la page et le préchargement au survol du
// menu (`usePrefetchPage`) lisent ainsi la même entrée du cache.
export const charactersQuery = queryOptions({
  queryKey: KEYS.characters,
  queryFn: () => unwrap(api.GET("/api/characters/")),
});

export function useCharacters() {
  return useQuery(charactersQuery);
}

export const membersQuery = queryOptions({
  queryKey: KEYS.members,
  queryFn: () => unwrap(api.GET("/api/members/")),
});

export function useMembers() {
  return useQuery(membersQuery);
}

export const pollsQuery = queryOptions({
  queryKey: KEYS.polls,
  queryFn: () => unwrap(api.GET("/api/polls/")),
});

export function usePolls() {
  return useQuery(pollsQuery);
}

export function usePoll(id: number) {
  return useQuery({
    queryKey: KEYS.poll(id),
    queryFn: () => unwrap(api.GET("/api/polls/{id}/", { params: { path: { id } } })),
  });
}

/** Événements à venir (depuis hier) ou dans une fenêtre donnée. */
export function eventsQuery(window?: { from: string; to: string }) {
  return queryOptions({
    queryKey: window ? KEYS.eventsWindow(window.from, window.to) : KEYS.events,
    queryFn: () => unwrap(api.GET("/api/events/", { params: { query: window } })),
  });
}

export function useEvents(window?: { from: string; to: string }) {
  return useQuery(eventsQuery(window));
}

export function useEvent(id: number) {
  return useQuery({
    queryKey: KEYS.event(id),
    queryFn: () => unwrap(api.GET("/api/events/{id}/", { params: { path: { id } } })),
  });
}

export function useEquipmentSets(characterId: number) {
  return useQuery({
    queryKey: KEYS.equipmentSets(characterId),
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_pk}/equipment-sets/", {
          params: { path: { character_pk: characterId } },
        }),
      ),
  });
}

export function useTalentBuilds(characterId: number) {
  return useQuery({
    queryKey: KEYS.talentBuilds(characterId),
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_pk}/talent-builds/", {
          params: { path: { character_pk: characterId } },
        }),
      ),
  });
}

export function useClassTalents(slug: string) {
  return useQuery({
    queryKey: KEYS.classTalents(slug),
    queryFn: () => unwrap(api.GET("/api/talents/{slug}/", { params: { path: { slug } } })),
    staleTime: Infinity,
  });
}

export const guildAvailabilityQuery = queryOptions({
  queryKey: KEYS.guildAvailability,
  queryFn: () => unwrap(api.GET("/api/availability/")),
});

export function useGuildAvailability() {
  return useQuery(guildAvailabilityQuery);
}

export function useMyAvailability() {
  return useQuery({
    queryKey: KEYS.myAvailability,
    queryFn: () => unwrap(api.GET("/api/auth/me/availability/")),
  });
}

export function useSyncPending() {
  return useQuery({ queryKey: KEYS.syncPending, queryFn: () => unwrap(api.GET("/api/sync/pending/")) });
}

export function useSyncDevices() {
  return useQuery({ queryKey: KEYS.syncDevices, queryFn: () => unwrap(api.GET("/api/sync/devices/")) });
}

export function useSyncImports() {
  return useQuery({ queryKey: KEYS.syncImports, queryFn: () => unwrap(api.GET("/api/sync/imports/")) });
}

/** Dernière release du compagnon ; `null` tant qu'aucune n'est publiée (204). */
export function useSyncRelease() {
  return useQuery({
    queryKey: KEYS.syncRelease,
    staleTime: 60 * 60_000,
    queryFn: async () => {
      const { data, error, response } = await api.GET("/api/sync/release/");
      if (response.status === 204) return null;
      if (error || data === undefined) throw error ?? new Error(`Erreur ${response.status}`);
      return data;
    },
  });
}

/** Invalide un groupe de requêtes après une mutation. */
export function useInvalidate() {
  const queryClient = useQueryClient();
  return (...keys: readonly (readonly unknown[])[]) =>
    Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

export { unwrap };
