import { useOutletContext } from "react-router";
import type { Member } from "@/api/client";

/** Utilisateur connecté, garanti présent sous `RequireAuth`. */
export function useCurrentUser(): Member {
  return useOutletContext<Member>();
}
