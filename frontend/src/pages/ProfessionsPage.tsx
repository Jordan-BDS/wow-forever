import { useMemo, useState } from "react";
import { Link } from "react-router";
import { useCharacters, useGameData } from "@/api/hooks";
import { ClassDot, ClassName } from "@/components/game";
import { Card, PageTitle, Select, Spinner } from "@/components/ui";
import { findClass } from "@/lib/game";

export function ProfessionsPage() {
  const characters = useCharacters();
  const gamedata = useGameData();
  const [filter, setFilter] = useState("");

  const rows = useMemo(() => {
    const list = [];
    for (const c of characters.data ?? []) {
      for (const p of c.professions ?? []) {
        if (!filter || p.profession === filter) list.push({ character: c, entry: p });
      }
    }
    return list.sort(
      (a, b) =>
        a.entry.profession.localeCompare(b.entry.profession) || (b.entry.skill ?? 0) - (a.entry.skill ?? 0),
    );
  }, [characters.data, filter]);

  if (characters.isPending || gamedata.isPending) return <Spinner />;
  const professions = gamedata.data?.professions ?? [];

  return (
    <>
      <PageTitle>Métiers de la guilde</PageTitle>
      <Card className="overflow-x-auto p-0">
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-3 text-sm">
          <Select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Métier">
            <option value="">Tous les métiers</option>
            {professions.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.name}
              </option>
            ))}
          </Select>
          <span className="ml-auto text-muted">
            {rows.length} ligne{rows.length > 1 && "s"}
          </span>
        </div>
        {rows.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted">
            Personne n'a encore renseigné ce métier. Ça se fait sur la fiche de chaque personnage.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted">
              <tr>
                <th className="px-3 py-2">Métier</th>
                <th className="px-3 py-2">Niveau</th>
                <th className="px-3 py-2">Personnage</th>
                <th className="hidden px-3 py-2 sm:table-cell">Joueur</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ character, entry }) => {
                const profession = professions.find((p) => p.slug === entry.profession);
                const spec = profession?.specializations.find((s) => s.slug === entry.specialization);
                const playerClass = findClass(gamedata.data, character.player_class);
                return (
                  <tr key={`${character.id}-${entry.profession}`} className="border-t border-border/60">
                    <td className="px-3 py-2">
                      {profession?.name ?? entry.profession}
                      {spec && <span className="text-muted"> · {spec.name}</span>}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-24 overflow-hidden rounded bg-surface-2">
                          <div
                            className="h-full bg-gold"
                            style={{ width: `${((entry.skill ?? 0) / 300) * 100}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs text-muted">{entry.skill}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <Link
                        to={`/personnages/${character.id}`}
                        className="flex items-center gap-2 hover:text-gold"
                      >
                        <ClassDot playerClass={playerClass} />
                        <ClassName playerClass={playerClass}>{character.name}</ClassName>
                      </Link>
                    </td>
                    <td className="hidden px-3 py-2 text-muted sm:table-cell">
                      {character.owner.display_name}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
