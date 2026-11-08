import { Link } from "react-router";
import { useGameData } from "@/api/hooks";
import { formatValue, useRankings } from "@/api/sync";
import { ClassName } from "@/components/game";
import { TitleCards } from "@/components/TitleBadges";
import { Card } from "@/components/ui";
import { findClass } from "@/lib/game";

/** Les catégories qui donnent un Roxor, avec le nom du titre en jeu. */
const RACES: { key: string; title: string }[] = [
  { key: "gathering_total", title: "Farmeur chinois" },
  { key: "hk", title: "Calamité de la Horde" },
  { key: "boss_kills", title: "Fléau des boss" },
  { key: "kills", title: "Machine à tuer" },
  { key: "deaths", title: "Lord Fragilux" },
  { key: "crafted_total", title: "MacGyver" },
  { key: "quests", title: "Larbin de Hurlevent" },
  { key: "fishing", title: "Nat Pagle" },
];

/** Accueil : les Roxors de la semaine passée (définitifs), puis la course en cours vers les prochains. */
export function WeekWidget() {
  const rankings = useRankings("week", "player");
  const gamedata = useGameData();
  const data = rankings.data;
  if (!data || data.characters === 0) return null;
  const races = RACES.map((r) => ({ ...r, category: data.categories.find((c) => c.key === r.key) })).filter(
    (r) => r.category && r.category.entries.length > 0,
  );
  if (races.length === 0 && data.titles.length === 0) return null;
  return (
    <>
      {data.titles.length > 0 && (
        <section className="md:col-span-2">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-lg">Roxors de la semaine passée</h2>
            <Link to="/classements" className="text-sm">
              Tous les classements
            </Link>
          </div>
          <TitleCards titles={data.titles} mob={data.mob_of_week.previous} />
        </section>
      )}
      {races.length > 0 && (
        <Card className="md:col-span-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-lg">Futurs Roxors</h2>
            <span className="text-xs text-muted">
              semaine en cours, depuis lundi · provisoire, clos dimanche minuit
            </span>
          </div>
          <div className="mt-4 grid gap-x-10 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
            {races.map(({ key, title, category }) => (
              <div key={key} className="text-sm">
                <div className={category!.shame ? "text-danger" : "text-gold-light"}>{title}</div>
                <div className="text-xs text-muted">{category!.label}</div>
                <ol className="mt-2 space-y-1">
                  {category!.entries.slice(0, 3).map((e) => (
                    <li key={e.user.id} className="flex justify-between gap-6">
                      <span className="truncate">
                        <span className="mr-1 inline-block w-5 text-right text-muted">{e.rank}.</span>
                        {e.character ? (
                          <Link to={`/personnages/${e.character.id}`}>
                            <ClassName playerClass={findClass(gamedata.data, e.character.player_class)}>
                              {e.character.name}
                            </ClassName>
                          </Link>
                        ) : (
                          <Link to={`/membres/${e.user.id}`}>{e.user.display_name}</Link>
                        )}
                      </span>
                      <span className="font-mono text-muted">{formatValue(category!, e.value)}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
            {data.mobs.length > 0 && (
              <div className="text-sm">
                <div className="text-gold-light">Souffre-douleur</div>
                <div className="text-xs text-muted">Créatures les plus tuées</div>
                <ol className="mt-2 space-y-1">
                  {data.mobs.slice(0, 3).map((m, i) => (
                    <li key={m.key} className="flex justify-between gap-6">
                      <span className="truncate">
                        <span className="mr-1 inline-block w-5 text-right text-muted">{i + 1}.</span>
                        {m.name}
                      </span>
                      <span className="shrink-0 font-mono text-muted">{m.kills}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        </Card>
      )}
    </>
  );
}
