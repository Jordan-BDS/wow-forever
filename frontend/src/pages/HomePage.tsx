import { Link } from "react-router";
import { useGuild } from "@/api/guild";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Card, PageTitle } from "@/components/ui";
import { FACTION_LABELS } from "@/lib/roles";

export function HomePage() {
  const me = useCurrentUser();
  const guild = useGuild();

  return (
    <>
      <PageTitle>Bienvenue, {me.display_name}</PageTitle>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="font-display text-lg">La guilde</h2>
          {guild.data ? (
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted">Nom</dt>
              <dd>{guild.data.name || <em className="text-muted">à décider</em>}</dd>
              <dt className="text-muted">Faction</dt>
              <dd>{FACTION_LABELS[guild.data.faction ?? ""]}</dd>
              <dt className="text-muted">Royaume</dt>
              <dd>{guild.data.realm || <em className="text-muted">à choisir</em>}</dd>
            </dl>
          ) : (
            <p className="mt-3 text-sm text-muted">Chargement…</p>
          )}
          <p className="mt-4 text-sm">
            <Link to="/guilde">Voir les paramètres</Link>
          </p>
        </Card>
        <Card>
          <h2 className="font-display text-lg">Prochaines étapes</h2>
          <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-muted">
            <li>Roster et personnages</li>
            <li>Métiers de la guilde</li>
            <li>Sondage pour le nom de la guilde</li>
            <li>Agenda des sorties</li>
          </ul>
        </Card>
      </div>
    </>
  );
}
