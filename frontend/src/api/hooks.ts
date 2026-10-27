import { useQuery, useQueryClient } from "@tanstack/react-query";
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
};

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error || data === undefined) throw error ?? new Error(`Erreur ${response.status}`);
  return data;
}

export function useGameData() {
  return useQuery({
    queryKey: KEYS.gamedata,
    queryFn: () => unwrap(api.GET("/api/gamedata/")),
    staleTime: Infinity,
  });
}

export function useCharacters() {
  return useQuery({ queryKey: KEYS.characters, queryFn: () => unwrap(api.GET("/api/characters/")) });
}

export function useMembers() {
  return useQuery({ queryKey: KEYS.members, queryFn: () => unwrap(api.GET("/api/members/")) });
}

export function usePolls() {
  return useQuery({ queryKey: KEYS.polls, queryFn: () => unwrap(api.GET("/api/polls/")) });
}

export function usePoll(id: number) {
  return useQuery({
    queryKey: KEYS.poll(id),
    queryFn: () => unwrap(api.GET("/api/polls/{id}/", { params: { path: { id } } })),
  });
}

/** Événements à venir (depuis hier) ou dans une fenêtre donnée. */
export function useEvents(window?: { from: string; to: string }) {
  return useQuery({
    queryKey: window ? KEYS.eventsWindow(window.from, window.to) : KEYS.events,
    queryFn: () => unwrap(api.GET("/api/events/", { params: { query: window } })),
  });
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

export function useGuildAvailability() {
  return useQuery({
    queryKey: KEYS.guildAvailability,
    queryFn: () => unwrap(api.GET("/api/availability/")),
  });
}

export function useMyAvailability() {
  return useQuery({
    queryKey: KEYS.myAvailability,
    queryFn: () => unwrap(api.GET("/api/auth/me/availability/")),
  });
}

/** Invalide un groupe de requêtes après une mutation. */
export function useInvalidate() {
  const queryClient = useQueryClient();
  return (...keys: readonly (readonly unknown[])[]) =>
    Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

export { unwrap };
