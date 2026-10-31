import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { useClassTalents, useGameData } from "@/api/hooks";
import { ClassName } from "@/components/game";
import { TalentTrees } from "@/components/TalentTrees";
import { Button, Card, PageTitle, Select, Spinner } from "@/components/ui";
import { findClass } from "@/lib/game";
import {
  MAX_POINTS,
  type Build,
  decodeBuild,
  dominantTree,
  encodeBuild,
  pointsInTree,
  totalPoints,
} from "@/lib/talents";
import { useWowheadTooltips } from "@/lib/wowhead";

/** Calculateur vierge, sans personnage : le build vit dans l'URL (`?c=classe&t=code`). */
export function TalentsPage() {
  const gamedata = useGameData();
  const [params, setParams] = useSearchParams();
  const classSlug = params.get("c") ?? "warrior";
  const encoded = params.get("t") ?? "";
  const talents = useClassTalents(classSlug);
  const trees = useMemo(
    () => [...(talents.data?.trees ?? [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    [talents.data],
  );
  const [build, setBuild] = useState<Build>({});
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (trees.length) setBuild(decodeBuild(trees, encoded));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trees]);
  useWowheadTooltips([trees]);

  const update = (next: Build) => {
    setBuild(next);
    const code = encodeBuild(trees, next);
    setParams(
      (p) => {
        p.set("c", classSlug);
        if (code.replace(/-/g, "")) p.set("t", code);
        else p.delete("t");
        return p;
      },
      { replace: true },
    );
    setCopied(false);
  };

  const spent = totalPoints(trees, build);
  const playerClass = findClass(gamedata.data, classSlug);
  const dominant = dominantTree(trees, build);

  return (
    <>
      <PageTitle
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={classSlug}
              onChange={(e) => {
                setBuild({});
                setParams({ c: e.target.value }, { replace: true });
              }}
              aria-label="Classe"
            >
              {gamedata.data?.classes.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.name}
                </option>
              ))}
            </Select>
            <Button variant="ghost" disabled={spent === 0} onClick={() => update({})}>
              Réinitialiser
            </Button>
            <Button
              variant="ghost"
              disabled={spent === 0}
              onClick={() => navigator.clipboard?.writeText(window.location.href).then(() => setCopied(true))}
            >
              {copied ? "Lien copié ✓" : "Copier le lien"}
            </Button>
          </div>
        }
      >
        Calculateur de talents
      </PageTitle>

      <p className="mb-4 text-sm text-muted">
        <ClassName playerClass={playerClass}>{playerClass?.name}</ClassName> ·{" "}
        <strong className={spent === MAX_POINTS ? "text-gold" : "text-text"}>
          {spent} / {MAX_POINTS}
        </strong>{" "}
        points
        {dominant && ` · ${dominant.name}`}
        {trees.map((t) => ` · ${t.name} ${pointsInTree(t, build)}`)}
        <span className="block text-xs">
          Clic gauche : + 1 point. Clic droit (ou le petit − sur mobile) : − 1 point. Survole un talent pour
          sa description Wowhead.
        </span>
      </p>

      {talents.isPending ? (
        <Spinner />
      ) : trees.length === 0 ? (
        <Card className="text-sm text-muted">
          Pas de talents importés pour cette classe. Lance `import_gamedata` côté serveur.
        </Card>
      ) : (
        <TalentTrees
          trees={trees}
          build={build}
          onAdd={(t) => update({ ...build, [t.id]: (build[t.id] ?? 0) + 1 })}
          onRemove={(t) => update({ ...build, [t.id]: build[t.id] - 1 })}
        />
      )}
    </>
  );
}
