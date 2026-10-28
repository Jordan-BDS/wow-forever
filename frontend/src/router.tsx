import { createBrowserRouter } from "react-router";
import { RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import { SectionLayout } from "./components/SectionLayout";
import { AgendaPage } from "./pages/AgendaPage";
import { AvailabilityPage } from "./pages/AvailabilityPage";
import { EventFormPage } from "./pages/EventFormPage";
import { EventPage } from "./pages/EventPage";
import { CharacterFormPage } from "./pages/CharacterFormPage";
import { CharacterPage } from "./pages/CharacterPage";
import { CharactersPage } from "./pages/CharactersPage";
import { CraftsPage } from "./pages/CraftsPage";
import { GuildPage } from "./pages/GuildPage";
import { HomePage } from "./pages/HomePage";
import { ItemsPage } from "./pages/ItemsPage";
import { LoginPage } from "./pages/LoginPage";
import { MemberPage } from "./pages/MemberPage";
import { MembersPage } from "./pages/MembersPage";
import { PollPage } from "./pages/PollPage";
import { PollsPage } from "./pages/PollsPage";
import { ProfessionsPage } from "./pages/ProfessionsPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RankingsPage } from "./pages/RankingsPage";
import { RecipesPage } from "./pages/RecipesPage";
import { RosterPage } from "./pages/RosterPage";
import { TalentsPage } from "./pages/TalentsPage";

export const router = createBrowserRouter([
  { path: "/login", Component: LoginPage },
  {
    path: "/",
    Component: RequireAuth,
    children: [
      {
        Component: Layout,
        children: [
          { index: true, Component: HomePage },
          { path: "personnages", Component: CharactersPage },
          { path: "personnages/nouveau", Component: CharacterFormPage },
          { path: "personnages/:id", Component: CharacterPage },
          { path: "personnages/:id/modifier", Component: CharacterFormPage },
          { path: "agenda", Component: AgendaPage },
          { path: "agenda/nouveau", Component: EventFormPage },
          { path: "agenda/:id", Component: EventPage },
          { path: "agenda/:id/modifier", Component: EventFormPage },
          { path: "profil", Component: ProfilePage },
          {
            Component: SectionLayout,
            children: [
              { path: "roster", Component: RosterPage },
              { path: "membres", Component: MembersPage },
              { path: "membres/:id", Component: MemberPage },
              { path: "disponibilites", Component: AvailabilityPage },
              { path: "sondages", Component: PollsPage },
              { path: "sondages/:id", Component: PollPage },
              { path: "classements", Component: RankingsPage },
              { path: "guilde", Component: GuildPage },
              { path: "crafts", Component: CraftsPage },
              { path: "metiers", Component: ProfessionsPage },
              { path: "objets", Component: ItemsPage },
              { path: "talents", Component: TalentsPage },
              { path: "recettes", Component: RecipesPage },
            ],
          },
        ],
      },
    ],
  },
]);
