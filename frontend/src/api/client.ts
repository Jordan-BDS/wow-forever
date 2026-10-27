import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Member = components["schemas"]["Member"];
export type GuildSettings = components["schemas"]["GuildSettings"];
export type SiteRole = Member["site_role"];
export type Faction = NonNullable<GuildSettings["faction"]>;
export type Owner = components["schemas"]["Owner"];
export type GameData = components["schemas"]["GameData"];
export type PlayerClass = components["schemas"]["PlayerClass"];
export type Race = components["schemas"]["Race"];
export type Profession = components["schemas"]["Profession"];
export type Character = components["schemas"]["Character"];
export type CharacterRequest = components["schemas"]["CharacterRequest"];
export type CharacterProfessionRequest = components["schemas"]["CharacterProfessionRequest"];
export type GameRole = Character["main_role"];
export type AvailabilitySlot = components["schemas"]["AvailabilitySlot"];
export type GuildAvailability = components["schemas"]["GuildAvailability"];
export type Poll = components["schemas"]["Poll"];
export type PollRequest = components["schemas"]["PollRequest"];
export type PollStatus = Poll["status"];
export type Proposal = components["schemas"]["Proposal"];

function readCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

/** Django attend l'en-tête X-CSRFToken sur toute requête qui modifie l'état. */
const csrf: Middleware = {
  onRequest({ request }) {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      const token = readCookie("csrftoken");
      if (token) request.headers.set("X-CSRFToken", token);
    }
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: "/", credentials: "same-origin" });
api.use(csrf);

/** Erreurs DRF par champ (les listes de messages sont réduites au premier). */
export function fieldErrors(error: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (error && typeof error === "object") {
    for (const [key, value] of Object.entries(error as Record<string, unknown>)) {
      if (typeof value === "string") out[key] = value;
      else if (Array.isArray(value) && typeof value[0] === "string") out[key] = value[0];
      else if (Array.isArray(value)) out[key] = "Vérifie les lignes de ce bloc.";
    }
  }
  return out;
}

/** Transforme une erreur DRF en message lisible. */
export function errorMessage(error: unknown): string {
  if (error && typeof error === "object") {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    const firstField = Object.values(error as Record<string, unknown>)[0];
    if (Array.isArray(firstField) && typeof firstField[0] === "string") return firstField[0];
  }
  return "Une erreur est survenue.";
}
