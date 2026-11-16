import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import "@fontsource/marcellus/400.css";
import "@fontsource/alegreya-sans/400.css";
import "@fontsource/alegreya-sans/400-italic.css";
import "@fontsource/alegreya-sans/500.css";
import "@fontsource/alegreya-sans/700.css";
import "./index.css";
import { guildQuery } from "./api/guild";
import { gameDataQuery } from "./api/hooks";
import { prefetchPage } from "./api/prefetch";
import { meQuery } from "./auth/useMe";
import { preloadPages, router } from "./router";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

// Les requêtes de presque toutes les pages partent avec celle du joueur connecté, sans attendre sa réponse :
// un aller-retour de moins à l'ouverture. Un visiteur non connecté reçoit deux refus, sans effet.
void queryClient.prefetchQuery(meQuery);
void queryClient.prefetchQuery(guildQuery);
void queryClient.prefetchQuery(gameDataQuery);
// De même pour les données de la page ouverte (accueil, agenda, classements…), quand elles sont connues d'avance.
prefetchPage(queryClient, window.location.pathname);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);

window.addEventListener("load", preloadPages, { once: true });
