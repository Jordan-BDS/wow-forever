import { queryOptions, useQuery } from "@tanstack/react-query";
import { api } from "./client";

export const GUILD_KEY = ["guild"] as const;

/** La requête des paramètres de guilde : partagée par `useGuild` et le préchargement du démarrage. */
export const guildQuery = queryOptions({
  queryKey: GUILD_KEY,
  queryFn: async () => {
    const { data, error } = await api.GET("/api/guild/");
    if (error || !data) throw new Error("Paramètres de guilde indisponibles");
    return data;
  },
});

export function useGuild() {
  return useQuery(guildQuery);
}
