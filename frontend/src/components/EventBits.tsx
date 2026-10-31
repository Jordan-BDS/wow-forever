import clsx from "clsx";
import { Link } from "react-router";
import type { GuildEvent } from "@/api/client";
import { useCurrentUser } from "@/auth/useCurrentUser";
import {
  EVENT_KIND_COLOR,
  EVENT_KIND_LABEL,
  EVENT_STATUS_LABEL,
  SIGNUP_STATUS_LABEL,
  formatLongDate,
  formatTime,
} from "@/lib/events";
import { Card } from "./ui";

export function KindBadge({ kind }: { kind: GuildEvent["kind"] }) {
  return (
    <span className={clsx("rounded px-1.5 py-0.5 text-xs font-semibold", EVENT_KIND_COLOR[kind])}>
      {EVENT_KIND_LABEL[kind]}
    </span>
  );
}

export function StatusBadge({ status }: { status: GuildEvent["effective_status"] }) {
  if (status === "planned") return null;
  return (
    <span
      className={clsx(
        "rounded border px-1.5 py-0.5 text-xs",
        status === "cancelled" ? "border-danger/60 text-danger" : "border-border text-muted",
      )}
    >
      {EVENT_STATUS_LABEL[status]}
    </span>
  );
}

/** Ligne d'événement pour les listes (agenda, accueil). */
export function EventRow({ event }: { event: GuildEvent }) {
  const me = useCurrentUser();
  const total = event.candidates.tank + event.candidates.heal + event.candidates.dps;
  return (
    <Link to={`/agenda/${event.id}`} className="block text-text hover:text-text">
      <Card
        className={clsx(
          "flex flex-wrap items-center gap-x-3 gap-y-1 py-3 transition hover:border-gold/50",
          event.effective_status !== "planned" && "opacity-60",
        )}
      >
        <div className="w-24 shrink-0 text-sm">
          <div className="capitalize text-muted">{formatLongDate(event.starts_at)}</div>
          <div className="font-mono text-lg">{formatTime(event.starts_at)}</div>
        </div>
        <div className="min-w-0 grow basis-40">
          <div className="flex flex-wrap items-center gap-2">
            <KindBadge kind={event.kind} />
            <span className="truncate font-display text-lg">{event.title}</span>
            <StatusBadge status={event.effective_status} />
          </div>
          <div className="text-xs text-muted">
            Organisé par {event.organizer.display_name}
            {event.organizer.id === me.id && " (toi)"}
            {event.min_level && ` · niveau ${event.min_level}+`}
          </div>
        </div>
        <div className="ml-auto text-right text-sm">
          <div>
            {total} inscrit{total > 1 && "s"}
            {event.max_size && <span className="text-muted"> / {event.max_size}</span>}
          </div>
          {event.my_signup ? (
            <div className="text-xs text-success">
              {SIGNUP_STATUS_LABEL[event.my_signup.status]}
              {event.my_signup.placement === "confirmed" && " · confirmé"}
              {event.my_signup.placement === "bench" && " · banc"}
            </div>
          ) : (
            event.signups_open && <div className="text-xs text-gold">Pas encore inscrit</div>
          )}
        </div>
      </Card>
    </Link>
  );
}
