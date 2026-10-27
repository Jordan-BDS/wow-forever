import { Link } from "react-router";
import { useGuild } from "@/api/guild";
import { useCharacters, useEvents, useGameData, usePolls } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { EventRow } from "@/components/EventBits";
import { ClassDot, ClassName, LevelBadge } from "@/components/game";
import { Button, Card, PageTitle } from "@/components/ui";
import { findClass, formatRemaining } from "@/lib/game";
import { FACTION_LABELS } from "@/lib/roles";
import { PollCard } from "./PollsPage";

export function HomePage() {
  const me = useCurrentUser();
  const guild = useGuild();
  const polls = usePolls();
  const events = useEvents();
  const characters = useCharacters();
  const gamedata = useGameData();

  const openPolls = (polls.data ?? []).filter((p) => p.status === "proposals" || p.status === "votes");
  const toVote = openPolls.filter((p) => p.my_vote_count === 0);
  const upcoming = (events.data ?? []).filter((e) => e.effective_status === "planned").slice(0, 5);
  const pending = upcoming.filter((e) => !e.my_signup && e.signups_open);
  const mine = (characters.data ?? []).filter((c) => c.owner.id === me.id);

  return (
    <>
      <PageTitle>Bienvenue, {me.display_name}</PageTitle>

      {toVote.length > 0 && (
        <section className="mb-6 space-y-3">
          {toVote.map((poll) => (
            <Card key={poll.id} className="flex flex-wrap items-center justify-between gap-3 border-gold/50">
              <div>
                <p className="text-xs uppercase text-gold">Sondage en cours</p>
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
            <h2 className="text-sm uppercase text-muted">
              Prochains événements
              {pending.length > 0 && (
                <span className="ml-2 text-gold">· {pending.length} sans réponse de ta part</span>
              )}
            </h2>
            <Link to="/agenda" className="text-sm">
              Tout l'agenda
            </Link>
          </div>
          {upcoming.length === 0 ? (
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

        <Card>
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg">Mes personnages</h2>
            <Link to="/personnages" className="text-sm">
              Tout voir
            </Link>
          </div>
          {mine.length === 0 ? (
            <p className="mt-3 text-sm text-muted">
              Tu n'as pas encore de personnage. <Link to="/personnages/nouveau">Crée le premier</Link> pour
              apparaître dans le roster.
            </p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {mine.map((c) => {
                const playerClass = findClass(gamedata.data, c.player_class);
                return (
                  <li key={c.id} className="flex items-center justify-between">
                    <Link
                      to={`/personnages/${c.id}`}
                      className="flex items-center gap-2 text-text hover:text-gold"
                    >
                      <ClassDot playerClass={playerClass} />
                      <ClassName playerClass={playerClass}>{c.name}</ClassName>
                      {c.is_main && <span className="text-xs text-muted">main</span>}
                    </Link>
                    <LevelBadge level={c.level ?? 1} />
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card>
          <h2 className="font-display text-lg">La guilde</h2>
          {guild.data ? (
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted">Nom</dt>
              <dd>{guild.data.name || <em className="text-muted">à décider par sondage</em>}</dd>
              <dt className="text-muted">Faction</dt>
              <dd>{FACTION_LABELS[guild.data.faction ?? ""]}</dd>
              <dt className="text-muted">Royaume</dt>
              <dd>{guild.data.realm || <em className="text-muted">à choisir</em>}</dd>
            </dl>
          ) : (
            <p className="mt-3 text-sm text-muted">Chargement…</p>
          )}
          <div className="mt-4 flex flex-wrap gap-3 text-sm">
            <Link to="/roster">Roster</Link>
            <Link to="/metiers">Métiers</Link>
            <Link to="/disponibilites">Disponibilités</Link>
          </div>
        </Card>

        {openPolls.length > 0 && (
          <section className="md:col-span-2">
            <h2 className="mb-2 text-sm uppercase text-muted">Sondages en cours</h2>
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
