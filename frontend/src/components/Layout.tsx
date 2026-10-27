import clsx from "clsx";
import { useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useGuild } from "@/api/guild";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { useLogout } from "@/auth/useMe";
import { SECTIONS, isSectionActive } from "@/lib/navigation";
import { Emblem } from "./Emblem";
import { Button, RoleBadge } from "./ui";

export function Layout() {
  const me = useCurrentUser();
  const guild = useGuild();
  const logout = useLogout();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const title = guild.data?.name || "WoW Forever";
  useEffect(() => {
    document.title = guild.data?.name ? `${guild.data.name} — WoW Forever` : "WoW Forever — Guilde";
  }, [guild.data?.name]);
  const subtitle = "Par des zouaves, pour des zouaves";

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
          <nav className="nav-scroll -mx-4 flex w-[calc(100%+2rem)] gap-1 overflow-x-auto px-4 text-sm sm:mx-0 sm:w-auto sm:basis-full sm:px-0">
            {SECTIONS.map((section) => {
              const active = isSectionActive(section, pathname);
              return (
                <NavLink
                  key={section.to}
                  to={section.to}
                  className={clsx(
                    "whitespace-nowrap px-3 py-2 transition-colors",
                    active
                      ? "text-gold shadow-[inset_0_-2px_0_var(--color-gold)]"
                      : "text-muted hover:text-text",
                  )}
                >
                  {section.label}
                </NavLink>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet context={me} />
      </main>
    </div>
  );
}
