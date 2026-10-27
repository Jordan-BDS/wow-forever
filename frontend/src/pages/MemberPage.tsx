import { Link, Navigate, useParams } from "react-router";
import { useCharacters, useGameData, useGuildAvailability, useMembers } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { AvailabilityGrid } from "@/components/AvailabilityGrid";
import { ClassDot, ClassName, GameRoleTag, LevelBadge } from "@/components/game";
import { Button, Card, PageTitle, RoleBadge, Spinner } from "@/components/ui";
import { namesByCell } from "@/lib/availability";
import { findClass } from "@/lib/game";

export function MemberPage() {
  const id = Number(useParams().id);
  const me = useCurrentUser();
  const members = useMembers();
  const characters = useCharacters();
  const gamedata = useGameData();
  const availability = useGuildAvailability();

  if (members.isPending || characters.isPending || gamedata.isPending) return <Spinner />;
  const member = members.data?.find((m) => m.id === id);
  if (!member) return <Navigate to="/membres" replace />;

  const chars = (characters.data ?? [])
    .filter((c) => c.owner.id === id)
    .sort((a, b) => Number(b.is_main) - Number(a.is_main) || (b.level ?? 0) - (a.level ?? 0));
  const slots = (availability.data ?? []).filter((s) => s.user === id);
  const isMe = member.id === me.id;

  return (
    <>
      <PageTitle
        actions={
          isMe && (
            <Link to="/profil">
              <Button variant="ghost">Modifier mon profil</Button>
            </Link>
          )
        }
      >
        <span className="flex items-center gap-3">
          <img src={member.avatar_url} alt="" className="size-10 rounded-full border border-border" />
          {member.display_name}
          <RoleBadge role={member.site_role} />
        </span>
      </PageTitle>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="font-display text-lg">Profil</h2>
          <p className="mt-1 text-xs text-muted">Discord : {member.discord_username}</p>
          <p className="mt-3 whitespace-pre-wrap text-sm">
            {member.bio || <em className="text-muted">Pas encore de bio.</em>}
          </p>
        </Card>

        <Card>
          <h2 className="font-display text-lg">Personnages</h2>
          {chars.length === 0 ? (
            <p className="mt-3 text-sm text-muted">Aucun personnage pour l'instant.</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {chars.map((c) => {
                const playerClass = findClass(gamedata.data, c.player_class);
                return (
                  <li key={c.id} className="flex items-center justify-between gap-3">
                    <Link to={`/personnages/${c.id}`} className="flex items-center gap-2 hover:text-gold">
                      <ClassDot playerClass={playerClass} />
                      <ClassName playerClass={playerClass}>{c.name}</ClassName>
                      {c.is_main && <span className="text-xs text-muted">main</span>}
                    </Link>
                    <span className="flex items-center gap-3">
                      <GameRoleTag role={c.main_role} />
                      <LevelBadge level={c.level ?? 1} />
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card className="md:col-span-2">
          <h2 className="font-display text-lg">Disponibilités</h2>
          {slots.length === 0 ? (
            <p className="mt-3 text-sm text-muted">Pas de créneaux renseignés.</p>
          ) : (
            <div className="mt-3">
              <AvailabilityGrid mode="heatmap" names={namesByCell(slots)} total={1} />
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
