import { Link } from "react-router";
import { formatValue, useRankings } from "@/api/sync";
import { TitleCards } from "@/components/TitleBadges";
import { Card } from "@/components/ui";

/** Les quatre catégories qui donnent un Roxor, avec le nom du titre en jeu. */
const RACES: { key: string; title: string }[] = [
  { key: "gathering_total", title: "Farmeur chinois" },
  { key: "hk", title: "Calamité de la Horde" },
  { key: "boss_kills", title: "Fléau des boss" },
  { key: "deaths", title: "Lord Fragilux" },
];

/** Accueil : les Roxors de la semaine passée (définitifs), puis la course en cours vers les prochains. */
export function WeekWidget() {
  const rankings = useRankings("week", "player");
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
          <TitleCards titles={data.titles} />
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
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {races.map(({ key, title, category }) => (
              <div key={key} className="text-sm">
                <div className={category!.shame ? "text-danger" : "text-gold-light"}>{title}</div>
                <div className="text-xs text-muted">{category!.label}</div>
                <ol className="mt-1 space-y-0.5">
                  {category!.entries.slice(0, 3).map((e) => (
                    <li key={e.user.id} className="flex justify-between gap-2">
                      <span>
                        <span className="text-muted">{e.rank}. </span>
                        <Link to={`/membres/${e.user.id}`}>{e.user.display_name}</Link>
                      </span>
                      <span className="font-mono text-muted">{formatValue(category!, e.value)}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}
