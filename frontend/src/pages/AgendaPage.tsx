import clsx from "clsx";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import type { GuildEvent } from "@/api/client";
import { useEvents } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { EventRow } from "@/components/EventBits";
import { Button, Card, PageTitle, Spinner } from "@/components/ui";
import { EVENT_KIND_COLOR, dateKey, formatMonth, formatTime, monthGrid } from "@/lib/events";
import { WEEKDAYS_SHORT } from "@/lib/game";

type View = "list" | "month";

export function AgendaPage() {
  const [view, setView] = useState<View>(() => (window.innerWidth < 768 ? "list" : "month"));
  const [mineOnly, setMineOnly] = useState(false);

  return (
    <>
      <PageTitle
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-md border border-border text-sm">
              {(["month", "list"] as View[]).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setView(v)}
                  className={clsx(
                    "px-3 py-1.5",
                    view === v ? "bg-surface-2 text-text" : "text-muted hover:text-text",
                  )}
                >
                  {v === "month" ? "Mois" : "Liste"}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-1.5 text-sm text-muted">
              <input
                type="checkbox"
                checked={mineOnly}
                onChange={(e) => setMineOnly(e.target.checked)}
                className="accent-gold"
              />
              Mes événements
            </label>
            <Link to="/agenda/nouveau">
              <Button>Nouvel événement</Button>
            </Link>
          </div>
        }
      >
        Agenda
      </PageTitle>
      {view === "month" ? <MonthView mineOnly={mineOnly} /> : <ListView mineOnly={mineOnly} />}
    </>
  );
}

function useMineFilter(mineOnly: boolean) {
  const me = useCurrentUser();
  return (event: GuildEvent) => !mineOnly || event.organizer.id === me.id || event.my_signup !== null;
}

function ListView({ mineOnly }: { mineOnly: boolean }) {
  const events = useEvents();
  const keep = useMineFilter(mineOnly);
  if (events.isPending) return <Spinner />;
  const list = (events.data ?? []).filter(keep);
  return (
    <div className="space-y-3">
      {list.length === 0 && (
        <p className="text-sm text-muted">
          Rien de prévu. <Link to="/agenda/nouveau">Propose une sortie</Link> !
        </p>
      )}
      {list.map((event) => (
        <EventRow key={event.id} event={event} />
      ))}
    </div>
  );
}

function MonthView({ mineOnly }: { mineOnly: boolean }) {
  const [cursor, setCursor] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });
  const weeks = useMemo(() => monthGrid(cursor.year, cursor.month), [cursor]);
  const first = weeks[0][0];
  const afterLast = new Date(weeks.at(-1)!.at(-1)!);
  afterLast.setDate(afterLast.getDate() + 1);
  const events = useEvents({ from: first.toISOString(), to: afterLast.toISOString() });
  const keep = useMineFilter(mineOnly);

  const byDay = useMemo(() => {
    const map = new Map<string, GuildEvent[]>();
    for (const event of (events.data ?? []).filter(keep)) {
      const key = dateKey(new Date(event.starts_at));
      map.set(key, [...(map.get(key) ?? []), event]);
    }
    return map;
  }, [events.data, keep]);

  const [todayKey] = useState(() => dateKey(new Date()));
  const shift = (delta: number) => {
    const d = new Date(cursor.year, cursor.month + delta, 1);
    setCursor({ year: d.getFullYear(), month: d.getMonth() });
  };

  return (
    <Card className="p-2 sm:p-4">
      <div className="mb-3 flex items-center justify-between">
        <Button variant="ghost" onClick={() => shift(-1)} aria-label="Mois précédent">
          ‹
        </Button>
        <h2 className="font-display text-lg capitalize">{formatMonth(cursor.year, cursor.month)}</h2>
        <Button variant="ghost" onClick={() => shift(1)} aria-label="Mois suivant">
          ›
        </Button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-xs text-muted">
        {WEEKDAYS_SHORT.map((d) => (
          <div key={d} className="py-1">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {weeks.flat().map((day) => {
          const key = dateKey(day);
          const inMonth = day.getMonth() === cursor.month;
          const dayEvents = byDay.get(key) ?? [];
          return (
            <div
              key={key}
              className={clsx(
                "min-h-14 rounded-md border p-1 text-xs sm:min-h-20",
                inMonth ? "border-border bg-bg/60" : "border-transparent text-muted/50",
                key === todayKey && "border-gold/60",
              )}
            >
              <div className={clsx("mb-1 text-right font-mono", key === todayKey && "text-gold")}>
                {day.getDate()}
              </div>
              <div className="space-y-1">
                {dayEvents.map((event) => (
                  <Link
                    key={event.id}
                    to={`/agenda/${event.id}`}
                    title={`${formatTime(event.starts_at)} ${event.title}`}
                    className={clsx(
                      // Sur mobile, une simple barre de couleur par événement ; le titre revient dès sm.
                      "block h-1.5 rounded hover:opacity-90 sm:h-auto sm:truncate sm:px-1 sm:py-0.5",
                      EVENT_KIND_COLOR[event.kind],
                      event.effective_status !== "planned" && "line-through opacity-50",
                    )}
                  >
                    <span className="hidden font-mono sm:inline">{formatTime(event.starts_at)} </span>
                    <span className="sr-only sm:not-sr-only">{event.title}</span>
                  </Link>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      {events.isPending && (
        <div className="mt-3 flex justify-center">
          <Spinner />
        </div>
      )}
    </Card>
  );
}
