// Préchargement des données d'une page au survol de son lien dans le menu : au clic, elles sont déjà là.
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { auctionsQuery, DEFAULT_AUCTION_FILTERS } from "./auctions";
import { bountiesQuery } from "./bounties";
import { charactersQuery, eventsQuery, guildAvailabilityQuery, membersQuery, pollsQuery } from "./hooks";
import { rankingsQuery, wantedQuery } from "./sync";

/** Par destination du menu, les requêtes que la page lance à son ouverture, avec ses réglages de départ. Une
 * page absente d'ici n'est pas préchargée (ses requêtes dépendent de ce que le joueur y saisit). */
const PAGE_QUERIES: Record<string, (client: QueryClient) => void> = {
  "/": (client) => {
    void client.prefetchQuery(eventsQuery());
    void client.prefetchQuery(pollsQuery);
    void client.prefetchQuery(rankingsQuery("week", "player"));
  },
  "/personnages": (client) => void client.prefetchQuery(charactersQuery),
  "/agenda": (client) => void client.prefetchQuery(eventsQuery()),
  "/roster": (client) => void client.prefetchQuery(charactersQuery),
  "/membres": (client) => void client.prefetchQuery(membersQuery),
  "/disponibilites": (client) => {
    void client.prefetchQuery(guildAvailabilityQuery);
    void client.prefetchQuery(membersQuery);
  },
  "/sondages": (client) => void client.prefetchQuery(pollsQuery),
  "/classements": (client) => void client.prefetchQuery(rankingsQuery("week", "player")),
  "/wanted": (client) => void client.prefetchQuery(wantedQuery("season")),
  "/primes": (client) => void client.prefetchQuery(bountiesQuery),
  "/hv": (client) => void client.prefetchQuery(auctionsQuery(DEFAULT_AUCTION_FILTERS)),
  "/metiers": (client) => void client.prefetchQuery(charactersQuery),
};

/** Lance les requêtes de la page `to`, si elle en a de connues d'avance. */
export function prefetchPage(client: QueryClient, to: string) {
  PAGE_QUERIES[to]?.(client);
}

/** À brancher sur le survol et le focus d'un lien du menu. Des données encore fraîches ne sont pas redemandées. */
export function usePrefetchPage() {
  const client = useQueryClient();
  return useCallback((to: string) => PAGE_QUERIES[to]?.(client), [client]);
}
