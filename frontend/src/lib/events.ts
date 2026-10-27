import type { EventKind, EventStatus, Instance, InstanceKind, Placement, SignupStatus } from "@/api/client";

export const EVENT_KINDS: EventKind[] = ["raid", "dungeon", "pvp", "social"];

export const EVENT_KIND_LABEL: Record<EventKind, string> = {
  raid: "Raid",
  dungeon: "Donjon",
  pvp: "PvP",
  social: "Social / autre",
};

/** Couleur de pastille par type d'événement (calendrier, listes). */
export const EVENT_KIND_COLOR: Record<EventKind, string> = {
  raid: "bg-horde text-white",
  dungeon: "bg-alliance text-white",
  pvp: "bg-gold text-bg",
  social: "bg-success text-bg",
};

/** Type d'instance attendu pour un type d'événement (null = pas d'instance). */
export const INSTANCE_KIND_FOR_EVENT: Record<EventKind, InstanceKind | null> = {
  raid: "raid",
  dungeon: "dungeon",
  pvp: "battleground",
  social: null,
};

export const EVENT_STATUS_LABEL: Record<EventStatus, string> = {
  planned: "Planifié",
  cancelled: "Annulé",
  done: "Terminé",
};

export const SIGNUP_STATUSES: SignupStatus[] = ["present", "maybe", "late", "absent"];

export const SIGNUP_STATUS_LABEL: Record<SignupStatus, string> = {
  present: "Présent",
  maybe: "Peut-être",
  late: "En retard",
  absent: "Absent",
};

export const PLACEMENTS: Placement[] = ["unplaced", "confirmed", "bench"];

export const PLACEMENT_LABEL: Record<Placement, string> = {
  unplaced: "Non placé",
  confirmed: "Confirmé",
  bench: "Banc",
};

export function instancesFor(instances: Instance[] | undefined, kind: EventKind): Instance[] {
  const expected = INSTANCE_KIND_FOR_EVENT[kind];
  return expected ? (instances ?? []).filter((i) => i.kind === expected) : [];
}

// --- calendrier ---------------------------------------------------------------

/** Clé locale « AAAA-MM-JJ » d'une date. */
export function dateKey(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Semaines (lundi → dimanche) couvrant un mois, chaque semaine étant un tableau de 7 dates à minuit. */
export function monthGrid(year: number, month: number): Date[][] {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7; // lundi = 0
  const start = new Date(year, month, 1 - offset);
  const weeks: Date[][] = [];
  const cursor = new Date(start);
  do {
    const week: Date[] = [];
    for (let i = 0; i < 7; i++) {
      week.push(new Date(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push(week);
  } while (cursor.getMonth() === month && cursor.getFullYear() === year);
  return weeks;
}

const monthFormat = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" });
const timeFormat = new Intl.DateTimeFormat("fr-FR", { timeStyle: "short", timeZone: "Europe/Paris" });
const longDateFormat = new Intl.DateTimeFormat("fr-FR", {
  weekday: "long",
  day: "numeric",
  month: "long",
  timeZone: "Europe/Paris",
});

export const formatMonth = (year: number, month: number) => monthFormat.format(new Date(year, month, 1));
export const formatTime = (iso: string) => timeFormat.format(new Date(iso));
export const formatLongDate = (iso: string) => longDateFormat.format(new Date(iso));
