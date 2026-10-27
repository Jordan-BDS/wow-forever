import { createBrowserRouter } from "react-router";
import { RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import { GuildPage } from "./pages/GuildPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { MembersPage } from "./pages/MembersPage";

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
          { path: "membres", Component: MembersPage },
          { path: "guilde", Component: GuildPage },
        ],
      },
    ],
  },
]);
