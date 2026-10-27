import clsx from "clsx";
import type { GameRole, PlayerClass } from "@/api/client";
import { ROLE_COLOR, ROLE_LABEL } from "@/lib/game";

/** Nom coloré à la couleur de classe (fond sombre : le blanc du prêtre reste lisible). */
export function ClassName({
  playerClass,
  children,
  className,
}: {
  playerClass: PlayerClass | undefined;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={clsx("font-medium", className)} style={{ color: playerClass?.color }}>
      {children}
    </span>
  );
}

export function ClassDot({ playerClass }: { playerClass: PlayerClass | undefined }) {
  return (
    <span
      className="inline-block size-2.5 rounded-full border border-black/30"
      style={{ background: playerClass?.color ?? "#777" }}
      title={playerClass?.name}
    />
  );
}

export function GameRoleTag({ role, muted }: { role: GameRole; muted?: boolean }) {
  return (
    <span className={clsx("text-xs font-semibold tracking-wide", muted ? "text-muted" : ROLE_COLOR[role])}>
      {ROLE_LABEL[role]}
    </span>
  );
}

export function LevelBadge({ level }: { level: number }) {
  return (
    <span
      className={clsx(
        "rounded border px-1.5 py-0.5 font-mono text-xs",
        level === 60 ? "border-gold/50 text-gold" : "border-border text-muted",
      )}
    >
      {level}
    </span>
  );
}
