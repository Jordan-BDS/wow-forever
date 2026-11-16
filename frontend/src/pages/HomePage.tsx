import { useState } from "react";
import { Link } from "react-router";
import { useEvents, usePolls } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { EventRow } from "@/components/EventBits";
import { Button, Card, PageTitle, Skeleton } from "@/components/ui";
import { formatRemaining } from "@/lib/game";
import { PollCard } from "./PollsPage";
import { WeekTitles, WeekWidget } from "@/components/WeekWidget";
import { LaunchCountdown } from "@/components/LaunchCountdown";
import { launchPhase } from "@/lib/launch";

export function HomePage() {
  const me = useCurrentUser();
  const [showCountdown] = useState(() => launchPhase(new Date()) !== "over");
  const polls = usePolls();
  const events = useEvents();

  const openPolls = (polls.data ?? []).filter((p) => p.status === "proposals" || p.status === "votes");
  const toVote = openPolls.filter((p) => p.my_vote_count === 0);
  const upcoming = (events.data ?? []).filter((e) => e.effective_status === "planned").slice(0, 5);
  const pending = upcoming.filter((e) => !e.my_signup && e.signups_open);

  return (
    <>
      <PageTitle>Bienvenue, {me.display_name}</PageTitle>

      <WeekTitles />

      {/* Le message de la guilde (GuildValues) n'est plus affiché pour le moment ; le serveur le garde. */}
      {showCountdown && (
        <div className="mb-8">
          <LaunchCountdown />
        </div>
      )}

      {toVote.length > 0 && (
        <section className="mb-6 space-y-3">
          {toVote.map((poll) => (
            <Card key={poll.id} className="flex flex-wrap items-center justify-between gap-3 border-gold/50">
              <div>
                <p className="text-xs text-gold">Sondage en cours</p>
                <p className="font-display text-lg">{poll.title}</p>
                <p className="text-xs text-muted">
                  Tu n'as pas encore voté · fin{" "}
                  {formatRemaining(poll.status === "proposals" ? poll.proposals_end : poll.votes_end)}
                </p>
              </div>
              <Link to={`/sondages/${poll.id}`}>
                <Button>Participer</Button>
              </Link>
            </Card>
          ))}
        </section>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <section className="md:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm text-muted">
              Prochains événements
              {pending.length > 0 && (
                <span className="ml-2 text-gold">· {pending.length} sans réponse de ta part</span>
              )}
            </h2>
            <Link to="/agenda" className="text-sm">
              Tout l'agenda
            </Link>
          </div>
          {events.isPending ? (
            <div role="status" aria-label="Chargement des événements" className="space-y-2">
              <Skeleton card className="h-[74px]" />
              <Skeleton card className="h-[74px]" />
              <Skeleton card className="h-[74px]" />
            </div>
          ) : events.isError ? (
            <Card className="text-sm text-danger">Les événements n'ont pas pu être chargés.</Card>
          ) : upcoming.length === 0 ? (
            <Card className="text-sm text-muted">
              Rien de prévu pour l'instant. <Link to="/agenda/nouveau">Propose une sortie</Link> !
            </Card>
          ) : (
            <div className="space-y-2">
              {upcoming.map((event) => (
                <EventRow key={event.id} event={event} />
              ))}
            </div>
          )}
        </section>

        <WeekWidget />

        {openPolls.length > 0 && (
          <section className="md:col-span-2">
            <h2 className="mb-2 text-sm text-muted">Sondages en cours</h2>
            <div className="space-y-3">
              {openPolls.map((p) => (
                <PollCard key={p.id} poll={p} />
              ))}
            </div>
          </section>
        )}
      </div>
    </>
  );
}
