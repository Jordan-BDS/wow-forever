import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router";
import type { Character, GameRole } from "@/api/client";
import { useCharacters, useGameData } from "@/api/hooks";
import { ClassDot, ClassName, GameRoleTag, LevelBadge } from "@/components/game";
import { Button, Card, PageTitle, Select, Spinner } from "@/components/ui";
import { GAME_ROLES, ROLE_LABEL, findClass, specName } from "@/lib/game";
import { COMPOSITION_MODES, type CompositionMode, groupByOwner, summarize } from "@/lib/roster";

export function RosterPage() {
  const characters = useCharacters();
  const gamedata = useGameData();
  const [classFilter, setClassFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState<GameRole | "">("");
  const [minLevel, setMinLevel] = useState(1);
  const [mode, setMode] = useState<CompositionMode>("mains");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const groups = useMemo(() => {
    const list = (characters.data ?? []).filter(
      (c) =>
        (!classFilter || c.player_class === classFilter) &&
        (!roleFilter || c.main_role === roleFilter || c.off_role === roleFilter) &&
        (c.level ?? 1) >= minLevel,
    );
    return groupByOwner(list);
  }, [characters.data, classFilter, roleFilter, minLevel]);

  const composition = useMemo(() => summarize(characters.data ?? [], mode), [characters.data, mode]);

  const toggle = (ownerId: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(ownerId)) next.delete(ownerId);
      else next.add(ownerId);
      return next;
    });

  if (characters.isPending || gamedata.isPending) return <Spinner />;

  return (
    <>
      <PageTitle
        actions={
          <Link to="/personnages/nouveau">
            <Button>Ajouter un personnage</Button>
          </Link>
        }
      >
        Roster
      </PageTitle>

      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <Card className="overflow-x-auto p-0">
          <div className="flex flex-wrap items-center gap-2 border-b border-border p-3 text-sm">
            <Select value={classFilter} onChange={(e) => setClassFilter(e.target.value)} aria-label="Classe">
              <option value="">Toutes les classes</option>
              {gamedata.data?.classes.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.name}
                </option>
              ))}
            </Select>
            <Select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value as GameRole | "")}
              aria-label="Rôle"
            >
              <option value="">Tous les rôles</option>
              {GAME_ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </Select>
            <label className="flex items-center gap-2 text-muted">
              Niveau ≥
              <input
                type="number"
                min={1}
                max={60}
                value={minLevel}
                onChange={(e) => setMinLevel(Number(e.target.value) || 1)}
                className="w-16 rounded-md border border-border bg-bg px-2 py-1 text-text"
              />
            </label>
            <span className="ml-auto text-muted">
              {groups.length} joueur{groups.length > 1 && "s"}
            </span>
          </div>

          {groups.length === 0 ? (
            <p className="p-6 text-center text-sm text-muted">
              Aucun personnage. <Link to="/personnages/nouveau">Ajoute le tien</Link> pour lancer le roster.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="px-3 py-2">Personnage</th>
                  <th className="px-3 py-2">Niveau</th>
                  <th className="px-3 py-2">Rôle</th>
                  <th className="hidden px-3 py-2 sm:table-cell">Spé</th>
                  <th className="hidden px-3 py-2 md:table-cell">Joueur</th>
                  <th className="px-3 py-2 text-right">Alts</th>
                </tr>
              </thead>
              <tbody>
                {groups.map(({ main, alts }) => (
                  <Fragment key={main.owner.id}>
                    <CharacterRow character={main} gamedata={gamedata.data}>
                      {alts.length > 0 && (
                        <button
                          type="button"
                          onClick={() => toggle(main.owner.id)}
                          className="rounded border border-border px-2 py-0.5 text-xs text-muted hover:bg-surface-2"
                          aria-expanded={expanded.has(main.owner.id)}
                        >
                          {alts.length} {expanded.has(main.owner.id) ? "▴" : "▾"}
                        </button>
                      )}
                    </CharacterRow>
                    {expanded.has(main.owner.id) &&
                      alts.map((alt) => (
                        <CharacterRow key={alt.id} character={alt} gamedata={gamedata.data} isAlt />
                      ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-display text-lg">Composition</h2>
            <div className="flex rounded-md border border-border text-xs">
              {COMPOSITION_MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => setMode(m.value)}
                  className={
                    mode === m.value
                      ? "bg-surface-2 px-2 py-1 text-text"
                      : "px-2 py-1 text-muted hover:text-text"
                  }
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          <div className="mb-4 grid grid-cols-3 gap-2 text-center">
            {GAME_ROLES.map((role) => (
              <div key={role} className="rounded-md border border-border bg-bg p-2">
                <div className="text-2xl font-semibold">{composition.roles[role]}</div>
                <GameRoleTag role={role} />
              </div>
            ))}
          </div>
          <ul className="space-y-1 text-sm">
            {gamedata.data?.classes
              .filter((c) => composition.classes[c.slug])
              .map((c) => (
                <li key={c.slug} className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <ClassDot playerClass={c} />
                    <ClassName playerClass={c}>{c.name}</ClassName>
                  </span>
                  <span className="text-muted">{composition.classes[c.slug]}</span>
                </li>
              ))}
            {composition.total === 0 && <li className="text-muted">Rien à afficher.</li>}
          </ul>
          <p className="mt-3 text-xs text-muted">{composition.total} personnage(s) comptés.</p>
        </Card>
      </div>
    </>
  );
}

function CharacterRow({
  character,
  gamedata,
  isAlt,
  children,
}: {
  character: Character;
  gamedata: ReturnType<typeof useGameData>["data"];
  isAlt?: boolean;
  children?: React.ReactNode;
}) {
  const playerClass = findClass(gamedata, character.player_class);
  return (
    <tr className={isAlt ? "border-t border-border/40 bg-bg/40 text-muted" : "border-t border-border/60"}>
      <td className="px-3 py-2">
        <Link to={`/personnages/${character.id}`} className="flex items-center gap-2 hover:text-gold">
          {isAlt && <span className="ml-3 text-muted">↳</span>}
          <ClassDot playerClass={playerClass} />
          <ClassName playerClass={playerClass}>{character.name}</ClassName>
        </Link>
      </td>
      <td className="px-3 py-2">
        <LevelBadge level={character.level ?? 1} />
      </td>
      <td className="px-3 py-2">
        <GameRoleTag role={character.main_role} />
        {character.off_role && (
          <>
            <span className="text-muted"> / </span>
            <GameRoleTag role={character.off_role as GameRole} muted />
          </>
        )}
      </td>
      <td className="hidden px-3 py-2 text-muted sm:table-cell">
        {specName(gamedata, character.specialization)}
      </td>
      <td className="hidden px-3 py-2 md:table-cell">
        <Link to={`/membres/${character.owner.id}`} className="text-text hover:text-gold">
          {character.owner.display_name}
        </Link>
      </td>
      <td className="px-3 py-2 text-right">{children}</td>
    </tr>
  );
}
