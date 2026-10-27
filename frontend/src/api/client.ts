import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Member = components["schemas"]["Member"];
export type GuildSettings = components["schemas"]["GuildSettings"];
export type SiteRole = Member["site_role"];
export type Faction = NonNullable<GuildSettings["faction"]>;

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
