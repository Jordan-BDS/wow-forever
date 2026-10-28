import { Link } from "react-router";
import { formatValue, useRankings } from "@/api/sync";
import { TitleChips } from "@/components/TitleBadges";
import { Card } from "@/components/ui";

const KEYS = ["boss_kills", "mining", "hk", "deaths"];

/** Accueil : top 3 de quelques classements de la semaine et titres en cours. */
export function WeekWidget() {
  const rankings = useRankings("week", "player");
  const data = rankings.data;
  if (!data || data.characters === 0) return null;
  const categories = data.categories.filter((c) => KEYS.includes(c.key) && c.entries.length > 0);
  if (categories.length === 0 && data.titles.length === 0) return null;
  return (
    <Card className="md:col-span-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-lg">Cette semaine</h2>
        <Link to="/classements" className="text-sm">
          Tous les classements
        </Link>
      </div>
      {data.titles.length > 0 && (
        <div className="mt-3">
          <TitleChips titles={data.titles} />
        </div>
      )}
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {categories.map((c) => (
          <div key={c.key} className="text-sm">
            <div className={c.shame ? "text-danger" : "text-gold-light"}>{c.label}</div>
            <ol className="mt-1 space-y-0.5">
              {c.entries.slice(0, 3).map((e) => (
                <li key={e.user.id} className="flex justify-between gap-2">
                  <span>
                    <span className="text-muted">{e.rank}. </span>
                    {e.user.display_name}
                  </span>
                  <span className="font-mono text-muted">{formatValue(c, e.value)}</span>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </Card>
  );
}
