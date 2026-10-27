import clsx from "clsx";
import { NavLink, Outlet, useLocation } from "react-router";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { SECTIONS, isSectionActive, visibleTabs } from "@/lib/navigation";

/** Sous-navigation d'une section (Guilde, Métiers, Données), puis la page. */
export function SectionLayout() {
  const me = useCurrentUser();
  const { pathname } = useLocation();
  const section = SECTIONS.find((s) => s.tabs && isSectionActive(s, pathname));
  const tabs = section ? visibleTabs(section, me.site_role) : [];

  return (
    <>
      {tabs.length > 0 && (
        <nav
          className="nav-scroll -mt-3 mb-6 flex gap-1 overflow-x-auto border-b border-border text-sm"
          aria-label={section?.label}
        >
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                clsx(
                  "whitespace-nowrap px-3 py-2 transition-colors",
                  isActive
                    ? "text-text shadow-[inset_0_-2px_0_var(--color-gold)]"
                    : "text-muted hover:text-text",
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      )}
      <Outlet context={me} />
    </>
  );
}
