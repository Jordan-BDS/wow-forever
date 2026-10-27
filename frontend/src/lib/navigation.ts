import type { SiteRole } from "@/api/client";

export interface NavTab {
  to: string;
  label: string;
  /** Réservé au GM. */
  gmOnly?: boolean;
}

export interface NavSection {
  label: string;
  /** Destination du clic sur l'onglet principal (premier sous-onglet). */
  to: string;
  /** Préfixes d'URL qui activent l'onglet. */
  match: string[];
  tabs?: NavTab[];
}

/** Six onglets : les pages génériques sont regroupées en sections avec des sous-onglets. */
export const SECTIONS: NavSection[] = [
  { label: "Accueil", to: "/", match: ["/"] },
  { label: "Personnages", to: "/personnages", match: ["/personnages"] },
  { label: "Agenda", to: "/agenda", match: ["/agenda"] },
  {
    label: "Guilde",
    to: "/roster",
    match: ["/roster", "/membres", "/disponibilites", "/sondages", "/guilde"],
    tabs: [
      { to: "/roster", label: "Roster" },
      { to: "/membres", label: "Membres" },
      { to: "/disponibilites", label: "Disponibilités" },
      { to: "/sondages", label: "Sondages" },
      { to: "/guilde", label: "Paramètres", gmOnly: true },
    ],
  },
  {
    label: "Métiers",
    to: "/crafts",
    match: ["/crafts", "/metiers"],
    tabs: [
      { to: "/crafts", label: "Crafts" },
      { to: "/metiers", label: "Métiers de la guilde" },
    ],
  },
  {
    label: "Données",
    to: "/objets",
    match: ["/objets", "/talents", "/recettes"],
    tabs: [
      { to: "/objets", label: "Objets" },
      { to: "/talents", label: "Talents" },
      { to: "/recettes", label: "Recettes" },
    ],
  },
];

export function isSectionActive(section: NavSection, pathname: string): boolean {
  return section.match.some((prefix) => (prefix === "/" ? pathname === "/" : pathname.startsWith(prefix)));
}

export function visibleTabs(section: NavSection, role: SiteRole): NavTab[] {
  return (section.tabs ?? []).filter((tab) => !tab.gmOnly || role === "gm");
}
