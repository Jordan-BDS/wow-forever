import clsx from "clsx";
import { NavLink, Outlet, useNavigate } from "react-router";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { useLogout } from "@/auth/useMe";
import { Button, RoleBadge } from "./ui";

const links = [
  { to: "/", label: "Accueil" },
  { to: "/membres", label: "Membres" },
  { to: "/guilde", label: "Guilde" },
];

export function Layout() {
  const me = useCurrentUser();
  const logout = useLogout();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border bg-surface/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <NavLink to="/" className="font-display text-lg text-gold hover:text-gold">
            WoW Forever
          </NavLink>
          <nav className="flex gap-1 text-sm">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === "/"}
                className={({ isActive }) =>
                  clsx(
                    "rounded-md px-3 py-1.5 transition hover:bg-surface-2",
                    isActive ? "bg-surface-2 text-text" : "text-muted",
                  )
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <img src={me.avatar_url} alt="" className="size-8 rounded-full border border-border" />
            <span className="hidden sm:inline">{me.display_name}</span>
            <RoleBadge role={me.site_role} />
            <Button
              variant="ghost"
              disabled={logout.isPending}
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
            >
              Déconnexion
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        <Outlet context={me} />
      </main>
    </div>
  );
}
