import clsx from "clsx";
import { NavLink, Outlet, useNavigate } from "react-router";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { useLogout } from "@/auth/useMe";
import { Button, RoleBadge } from "./ui";

const links = [
  { to: "/", label: "Accueil" },
  { to: "/agenda", label: "Agenda" },
  { to: "/roster", label: "Roster" },
  { to: "/metiers", label: "Métiers" },
  { to: "/objets", label: "Objets" },
  { to: "/talents", label: "Talents" },
  { to: "/disponibilites", label: "Dispos" },
  { to: "/sondages", label: "Sondages" },
  { to: "/membres", label: "Membres" },
];

export function Layout() {
  const me = useCurrentUser();
  const logout = useLogout();
  const navigate = useNavigate();
  const navLinks = me.site_role === "gm" ? [...links, { to: "/guilde", label: "Paramètres" }] : links;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border bg-surface/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <NavLink to="/" className="font-display text-lg text-gold hover:text-gold">
            WoW Forever
          </NavLink>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <NavLink to="/profil" className="flex items-center gap-2 text-text hover:text-gold">
              <img src={me.avatar_url} alt="" className="size-8 rounded-full border border-border" />
              <span className="hidden sm:inline">{me.display_name}</span>
            </NavLink>
            <RoleBadge role={me.site_role} />
            <Button
              variant="ghost"
              disabled={logout.isPending}
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
            >
              Déconnexion
            </Button>
          </div>
          <nav className="-mx-4 flex w-[calc(100%+2rem)] gap-1 overflow-x-auto px-4 text-sm sm:mx-0 sm:w-auto sm:basis-full sm:px-0">
            {navLinks.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === "/"}
                className={({ isActive }) =>
                  clsx(
                    "whitespace-nowrap rounded-md px-3 py-1.5 transition hover:bg-surface-2",
                    isActive ? "bg-surface-2 text-text" : "text-muted",
                  )
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet context={me} />
      </main>
    </div>
  );
}
