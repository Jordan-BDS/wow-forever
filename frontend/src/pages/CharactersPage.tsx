import { Link } from "react-router";
import type { Character, GameRole } from "@/api/client";
import { useCharacters, useGameData } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { ClassName, GameRoleTag, LevelBadge } from "@/components/game";
import { PageTitle, Spinner } from "@/components/ui";
import { findClass, findRace, specName } from "@/lib/game";

/** Mes personnages en cartes, avec une carte « + » pour en créer un. */
export function CharactersPage() {
  const me = useCurrentUser();
  const characters = useCharacters();
  const gamedata = useGameData();

  if (characters.isPending || gamedata.isPending) return <Spinner />;
  const mine = (characters.data ?? [])
    .filter((c) => c.owner.id === me.id)
    .sort((a, b) => Number(b.is_main) - Number(a.is_main) || (b.level ?? 0) - (a.level ?? 0));

  return (
    <>
      <PageTitle>Mes personnages</PageTitle>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {mine.map((character) => (
          <CharacterCard key={character.id} character={character} gamedata={gamedata.data} />
        ))}
        <Link
          to="/personnages/nouveau"
          className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border bg-surface/40 text-muted transition hover:border-gold hover:text-gold"
        >
          <span className="text-4xl leading-none">+</span>
          <span className="text-sm">
            {mine.length === 0 ? "Créer mon premier personnage" : "Ajouter un personnage"}
          </span>
        </Link>
      </div>
      <p className="mt-6 text-sm text-muted">
        Les personnages de toute la guilde sont dans le <Link to="/roster">roster</Link>.
      </p>
    </>
  );
}

function CharacterCard({
  character,
  gamedata,
}: {
  character: Character;
  gamedata: ReturnType<typeof useGameData>["data"];
}) {
  const playerClass = findClass(gamedata, character.player_class);
  const race = findRace(gamedata, character.race);
  const professions = (character.professions ?? []).map((p) => {
    const profession = gamedata?.professions.find((x) => x.slug === p.profession);
    return `${profession?.name ?? p.profession} ${p.skill}`;
  });
  return (
    <Link
      to={`/personnages/${character.id}`}
      className="group flex min-h-40 flex-col rounded-lg border border-border bg-surface p-4 text-text shadow-lg transition hover:border-gold/60 hover:text-text"
      style={{ borderTopColor: playerClass?.color, borderTopWidth: 3 }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <ClassName playerClass={playerClass} className="block truncate font-display text-xl">
            {character.name}
          </ClassName>
          <div className="text-xs text-muted">
            {race?.name} · {playerClass?.name}
            {character.specialization && ` · ${specName(gamedata, character.specialization)}`}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <LevelBadge level={character.level ?? 1} />
          {character.is_main && (
            <span className="rounded border border-gold/50 px-1.5 text-[10px] uppercase text-gold">main</span>
          )}
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2 text-sm">
        <GameRoleTag role={character.main_role} />
        {character.off_role && (
          <>
            <span className="text-muted">/</span>
            <GameRoleTag role={character.off_role as GameRole} muted />
          </>
        )}
      </div>
      <div className="mt-auto pt-3 text-xs text-muted">
        {professions.length > 0 ? professions.join(" · ") : "Aucun métier renseigné"}
      </div>
    </Link>
  );
}
