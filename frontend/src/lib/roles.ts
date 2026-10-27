import type { Faction, SiteRole } from "@/api/client";

export const ROLE_LABELS: Record<SiteRole, string> = {
  member: "Membre",
  officer: "Officier",
  gm: "GM",
};

export const ROLE_RANK: Record<SiteRole, number> = { member: 0, officer: 1, gm: 2 };

export const ROLES: SiteRole[] = ["member", "officer", "gm"];

export function isOfficerOrAbove(role: SiteRole): boolean {
  return ROLE_RANK[role] >= ROLE_RANK.officer;
}

export function outranks(actor: SiteRole, target: SiteRole): boolean {
  return ROLE_RANK[actor] > ROLE_RANK[target];
}

export const FACTION_LABELS: Record<Faction, string> = {
  alliance: "Alliance",
  horde: "Horde",
  "": "Non choisie",
};

export const LOGIN_ERRORS: Record<string, string> = {
  not_member: "Tu n'es pas sur le serveur Discord de la guilde.",
  missing_role: "Tu dois avoir le rôle « Membre » sur le Discord de la guilde.",
  deactivated: "Ton compte a été désactivé par un officier.",
  discord_denied: "Tu as refusé la connexion Discord.",
  state_mismatch: "La connexion a expiré, recommence.",
  discord_error: "Discord n'a pas répondu, réessaie dans un instant.",
  not_configured: "La connexion Discord n'est pas encore configurée par le GM.",
};
