import type { ComponentType } from "react";
import { createBrowserRouter } from "react-router";
import { RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import { SectionLayout } from "./components/SectionLayout";
import { PageSpinner } from "./components/ui";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { PollsPage } from "./pages/PollsPage";

/** Les pages chargées à la demande : chacune est un fichier à part, hors du script de démarrage. L'accueil,
 * la connexion et les sondages (que l'accueil reprend) restent dans celui-ci. */
const PAGES = {
  AgendaPage: () => import("./pages/AgendaPage").then((m) => m.AgendaPage),
  AuctionsPage: () => import("./pages/AuctionsPage").then((m) => m.AuctionsPage),
  AvailabilityPage: () => import("./pages/AvailabilityPage").then((m) => m.AvailabilityPage),
  BountiesPage: () => import("./pages/BountiesPage").then((m) => m.BountiesPage),
  CharacterFormPage: () => import("./pages/CharacterFormPage").then((m) => m.CharacterFormPage),
  CharacterPage: () => import("./pages/CharacterPage").then((m) => m.CharacterPage),
  CharactersPage: () => import("./pages/CharactersPage").then((m) => m.CharactersPage),
  CraftsPage: () => import("./pages/CraftsPage").then((m) => m.CraftsPage),
  EventFormPage: () => import("./pages/EventFormPage").then((m) => m.EventFormPage),
  EventPage: () => import("./pages/EventPage").then((m) => m.EventPage),
  GuildPage: () => import("./pages/GuildPage").then((m) => m.GuildPage),
  ItemsPage: () => import("./pages/ItemsPage").then((m) => m.ItemsPage),
  MemberPage: () => import("./pages/MemberPage").then((m) => m.MemberPage),
  MembersPage: () => import("./pages/MembersPage").then((m) => m.MembersPage),
  PollPage: () => import("./pages/PollPage").then((m) => m.PollPage),
  ProfessionsPage: () => import("./pages/ProfessionsPage").then((m) => m.ProfessionsPage),
  ProfilePage: () => import("./pages/ProfilePage").then((m) => m.ProfilePage),
  RankingsPage: () => import("./pages/RankingsPage").then((m) => m.RankingsPage),
  RecipesPage: () => import("./pages/RecipesPage").then((m) => m.RecipesPage),
  RosterPage: () => import("./pages/RosterPage").then((m) => m.RosterPage),
  TalentsPage: () => import("./pages/TalentsPage").then((m) => m.TalentsPage),
  TestsPage: () => import("./pages/TestsPage").then((m) => m.TestsPage),
  WantedPage: () => import("./pages/WantedPage").then((m) => m.WantedPage),
} satisfies Record<string, () => Promise<ComponentType>>;

const RELOADED = "wfg:page-reload";

/** `lazy` d'une route. Si le fichier de la page a disparu (le site a été redéployé depuis l'ouverture de
 * l'onglet), la page est rechargée une fois pour prendre la nouvelle version. */
function page(name: keyof typeof PAGES) {
  return async () => {
    try {
      return { Component: await PAGES[name]() };
    } catch (error) {
      let last = 0;
      try {
        last = Number(sessionStorage.getItem(RELOADED)) || 0;
        if (Date.now() - last > 60_000) sessionStorage.setItem(RELOADED, String(Date.now()));
      } catch {
        throw error;
      }
      if (Date.now() - last <= 60_000) throw error;
      window.location.reload();
      return new Promise<never>(() => {});
    }
  };
}

/** Une fois le site affiché et le navigateur au repos, les autres pages sont téléchargées en fond : changer de
 * page ne fait alors plus attendre. Pas en mode économie de données. */
export function preloadPages() {
  const connection = (navigator as { connection?: { saveData?: boolean } }).connection;
  if (connection?.saveData) return;
  const start = async () => {
    for (const load of Object.values(PAGES)) await load().catch(() => undefined);
  };
  if ("requestIdleCallback" in window) window.requestIdleCallback(() => void start(), { timeout: 5000 });
  else setTimeout(() => void start(), 3000);
}

export const router = createBrowserRouter([
  { path: "/login", Component: LoginPage },
  {
    path: "/",
    Component: RequireAuth,
    HydrateFallback: PageSpinner,
    children: [
      {
        Component: Layout,
        children: [
          { index: true, Component: HomePage },
          { path: "personnages", lazy: page("CharactersPage") },
          { path: "personnages/nouveau", lazy: page("CharacterFormPage") },
          { path: "personnages/:id", lazy: page("CharacterPage") },
          { path: "personnages/:id/modifier", lazy: page("CharacterFormPage") },
          { path: "agenda", lazy: page("AgendaPage") },
          { path: "agenda/nouveau", lazy: page("EventFormPage") },
          { path: "agenda/:id", lazy: page("EventPage") },
          { path: "agenda/:id/modifier", lazy: page("EventFormPage") },
          { path: "profil", lazy: page("ProfilePage") },
          {
            Component: SectionLayout,
            children: [
              { path: "roster", lazy: page("RosterPage") },
              { path: "membres", lazy: page("MembersPage") },
              { path: "membres/:id", lazy: page("MemberPage") },
              { path: "disponibilites", lazy: page("AvailabilityPage") },
              { path: "sondages", Component: PollsPage },
              { path: "sondages/:id", lazy: page("PollPage") },
              { path: "classements", lazy: page("RankingsPage") },
              { path: "wanted", lazy: page("WantedPage") },
              { path: "primes", lazy: page("BountiesPage") },
              { path: "guilde", lazy: page("GuildPage") },
              { path: "tests", lazy: page("TestsPage") },
              { path: "hv", lazy: page("AuctionsPage") },
              { path: "crafts", lazy: page("CraftsPage") },
              { path: "metiers", lazy: page("ProfessionsPage") },
              { path: "objets", lazy: page("ItemsPage") },
              { path: "talents", lazy: page("TalentsPage") },
              { path: "recettes", lazy: page("RecipesPage") },
            ],
          },
        ],
      },
    ],
  },
]);
