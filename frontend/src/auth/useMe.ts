import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Member } from "@/api/client";

export const ME_KEY = ["me"] as const;

async function fetchMe(): Promise<Member | null> {
  const { data, response } = await api.GET("/api/auth/me/");
  if (response.status === 401 || response.status === 403) return null;
  if (!response.ok || !data) throw new Error(`Erreur ${response.status}`);
  return data;
}

/** L'utilisateur connecté, `null` si personne n'est connecté. */
export function useMe() {
  return useQuery({ queryKey: ME_KEY, queryFn: fetchMe, staleTime: 5 * 60_000 });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.POST("/api/auth/logout/");
    },
    onSettled: () => {
      queryClient.setQueryData(ME_KEY, null);
      queryClient.clear();
    },
  });
}

export const discordLoginUrl = "/api/auth/discord/login/";
