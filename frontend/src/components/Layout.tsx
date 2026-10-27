import clsx from "clsx";
import { NavLink, Outlet, useNavigate } from "react-router";
import { useGuild } from "@/api/guild";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { useLogout } from "@/auth/useMe";
import { Emblem } from "./Emblem";
import { Button, RoleBadge } from "./ui";

const links = [
  { to: "/", label: "Accueil" },
  { to: "/personnages", label: "Personnages" },
  { to: "/agenda", label: "Agenda" },
  { to: "/roster", label: "Roster" },
  { to: "/metiers", label: "Métiers" },
  { to: "/crafts", label: "Crafts" },
  { to: "/objets", label: "Objets" },
  { to: "/talents", label: "Talents" },
  { to: "/disponibilites", label: "Dispos" },
  { to: "/sondages", label: "Sondages" },
  { to: "/membres", label: "Membres" },
];

export function Layout() {
  const me = useCurrentUser();
  const guild = useGuild();
  const logout = useLogout();
  const navigate = useNavigate();
  const navLinks = me.site_role === "gm" ? [...links, { to: "/guilde", label: "Paramètres" }] : links;
  const title = guild.data?.name || "WoW Forever";
  const subtitle = guild.data?.name
    ? [
        "Guilde",
        guild.data.faction === "alliance"
          ? "de l'Alliance"
          : guild.data.faction === "horde"
            ? "de la Horde"
            : null,
        guild.data.realm ? `· ${guild.data.realm}` : null,
      ]
        .filter(Boolean)
        .join(" ")
    : "La plateforme de la guilde";

  return (
    <div className="flex min-h-screen flex-col">
      <header className="banner pb-1.5">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 pt-3">
          <NavLink to="/" className="flex items-center gap-3 text-text hover:text-text">
            <Emblem className="size-11" />
            <span>
              <span className="block font-display text-xl leading-tight text-gold">{title}</span>
              <span className="block text-xs text-muted">{subtitle}</span>
            </span>
          </NavLink>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <NavLink to="/profil" className="flex items-center gap-2 text-text hover:text-gold">
              <img src={me.avatar_url} alt="" className="size-8 rounded-full border border-gold-dark/60" />
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
                    "whitespace-nowrap border-b-2 px-3 py-2 transition-colors",
                    isActive ? "border-gold text-gold" : "border-transparent text-muted hover:text-text",
                  )
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet context={me} />
      </main>
      <footer className="mx-auto w-full max-w-6xl px-4 pb-6 text-xs text-muted">
        <div className="rule-gold mb-3 opacity-50" />
        Pour la guilde, par la guilde. Infobulles et fiches détaillées fournies par Wowhead.
      </footer>
    </div>
  );
}
