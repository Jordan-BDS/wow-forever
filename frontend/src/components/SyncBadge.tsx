import clsx from "clsx";
import { useState } from "react";
import type { Character } from "@/api/client";
import { formatAgo, formatDateTime } from "@/lib/game";

/** Fraîcheur de la synchronisation depuis le jeu : vert < 7 j, orange au-delà, gris sans synchro. */
export function SyncBadge({ character, compact }: { character: Character; compact?: boolean }) {
  const [now] = useState(() => new Date()); // figé au montage : le badge n'a pas besoin de tourner en direct
  const synced = character.last_synced_at ?? null;
  if (!synced) {
    if (compact) return null;
    return (
      <span
        className="rounded border border-border px-1.5 text-[11px] text-muted"
        title="Jamais synchronisé depuis le jeu"
      >
        saisie manuelle
      </span>
    );
  }
  const ageDays = (now.getTime() - new Date(synced).getTime()) / 86_400_000;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded border px-1.5 text-[11px]",
        ageDays < 7 ? "border-success/60 text-success" : "border-[#d9a24a]/60 text-[#e2b86a]",
      )}
      title={`Synchronisé depuis le jeu le ${formatDateTime(synced)}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {compact ? formatAgo(synced, now) : `synchro ${formatAgo(synced, now)}`}
    </span>
  );
}

export function RolesToConfirmBadge({ character }: { character: Character }) {
  if (character.roles_confirmed !== false) return null;
  return (
    <span
      className="rounded border border-[#d9a24a]/60 px-1.5 text-[11px] text-[#e2b86a]"
      title="Créé par l'import : choisis ses rôles"
    >
      rôles à confirmer
    </span>
  );
}
