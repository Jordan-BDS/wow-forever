import type { GameData, GameRole, PlayerClass, PollStatus, Race } from "@/api/client";

export const GAME_ROLES: GameRole[] = ["tank", "heal", "dps"];

export const ROLE_LABEL: Record<GameRole, string> = { tank: "Tank", heal: "Heal", dps: "DPS" };

export const ROLE_COLOR: Record<GameRole, string> = {
  tank: "text-alliance",
  heal: "text-success",
  dps: "text-danger",
};

export const WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];
export const WEEKDAYS_SHORT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

export const POLL_STATUS_LABEL: Record<PollStatus, string> = {
  proposals: "Propositions ouvertes",
  votes: "Vote en cours",
  closed: "Clos, en attente de validation",
  validated: "Validé",
};

export function findClass(gamedata: GameData | undefined, slug: string): PlayerClass | undefined {
  return gamedata?.classes.find((c) => c.slug === slug);
}

export function findRace(gamedata: GameData | undefined, slug: string): Race | undefined {
  return gamedata?.races.find((r) => r.slug === slug);
}

export function specName(gamedata: GameData | undefined, slug: string | null | undefined): string {
  if (!slug) return "";
  for (const c of gamedata?.classes ?? []) {
    const spec = c.specializations.find((s) => s.slug === slug);
    if (spec) return spec.name;
  }
  return slug;
}

/** Races jouables pour une classe, dans la faction de la guilde (vide = pas encore choisie). */
export function racesFor(gamedata: GameData | undefined, classSlug: string, guildFaction: string): Race[] {
  return (gamedata?.races ?? []).filter(
    (race) =>
      race.classes.includes(classSlug) && (!race.faction || !guildFaction || race.faction === guildFaction),
  );
}

const dateTime = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Paris",
});

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

/** « dans 2 j 3 h », « dans 45 min », « terminé ». */
export function formatRemaining(iso: string, now = new Date()): string {
  const ms = new Date(iso).getTime() - now.getTime();
  if (ms <= 0) return "terminé";
  const minutes = Math.floor(ms / 60_000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (days > 0) return `dans ${days} j ${hours % 24} h`;
  if (hours > 0) return `dans ${hours} h ${minutes % 60} min`;
  return `dans ${Math.max(minutes, 1)} min`;
}

/** Valeur pour un <input type="datetime-local"> en heure locale. */
export function toLocalInput(iso: string | Date): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
