import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export const GUILD_KEY = ["guild"] as const;

export function useGuild() {
  return useQuery({
    queryKey: GUILD_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/guild/");
      if (error || !data) throw new Error("Paramètres de guilde indisponibles");
      return data;
    },
  });
}
