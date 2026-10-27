import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export const KEYS = {
  gamedata: ["gamedata"] as const,
  characters: ["characters"] as const,
  members: ["members"] as const,
  polls: ["polls"] as const,
  poll: (id: number) => ["polls", id] as const,
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
