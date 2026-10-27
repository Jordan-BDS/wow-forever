import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { api } from "@/api/client";
import { unwrap, useGameData } from "@/api/hooks";
import { ClassName } from "@/components/game";
import { Button, Card, PageTitle, Select, Spinner } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { useWowheadTooltips } from "@/lib/wowhead";
import { findClass } from "@/lib/game";
import {
  COLUMNS,
  MAX_POINTS,
  type Build,
  type TalentData,
  type TalentTreeData,
  canAdd,
  canRemove,
  decodeBuild,
  dominantTree,
  encodeBuild,
  pointsInTree,
  tierUnlocked,
  totalPoints,
} from "@/lib/talents";

export function TalentsPage() {
  const gamedata = useGameData();
  const [params, setParams] = useSearchParams();
  const classSlug = params.get("c") ?? "warrior";
  const encoded = params.get("t") ?? "";

  const talents = useQuery({
    queryKey: ["talents", classSlug],
    queryFn: () => unwrap(api.GET("/api/talents/{slug}/", { params: { path: { slug: classSlug } } })),
  });

  const trees = useMemo(
    () => [...(talents.data?.trees ?? [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    [talents.data],
  );
  const [build, setBuild] = useState<Build>({});
  const [copied, setCopied] = useState(false);

  // Charge le build encodé dans l'URL dès que les arbres sont connus.
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

  const changeClass = (slug: string) => {
    setBuild({});
    setParams({ c: slug }, { replace: true });
  };

  const spent = totalPoints(trees, build);
  const playerClass = findClass(gamedata.data, classSlug);
  const dominant = dominantTree(trees, build);

  return (
    <>
      <PageTitle
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Select value={classSlug} onChange={(e) => changeClass(e.target.value)} aria-label="Classe">
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
              onClick={() => {
                navigator.clipboard?.writeText(window.location.href).then(() => setCopied(true));
              }}
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
          Clic gauche : + 1 point. Clic droit : − 1 point. Survole un talent pour sa description Wowhead.
        </span>
      </p>

      {talents.isPending ? (
        <Spinner />
      ) : trees.length === 0 ? (
        <Card className="text-sm text-muted">
          Pas de talents importés pour cette classe. Lance `import_gamedata` côté serveur.
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {trees.map((tree) => (
            <TreeCard
              key={tree.id}
              tree={tree}
              trees={trees}
              build={build}
              onAdd={(t) => update({ ...build, [t.id]: (build[t.id] ?? 0) + 1 })}
              onRemove={(t) => update({ ...build, [t.id]: build[t.id] - 1 })}
            />
          ))}
        </div>
      )}
    </>
  );
}

function TreeCard({
  tree,
  trees,
  build,
  onAdd,
  onRemove,
}: {
  tree: TalentTreeData;
  trees: TalentTreeData[];
  build: Build;
  onAdd: (t: TalentData) => void;
  onRemove: (t: TalentData) => void;
}) {
  const rows = Math.max(...tree.talents.map((t) => t.row)) + 1;
  const grid: (TalentData | undefined)[][] = Array.from({ length: rows }, () =>
    Array(COLUMNS).fill(undefined),
  );
  for (const talent of tree.talents) grid[talent.row][talent.column] = talent;

  return (
    <Card className="p-3">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="font-display text-lg">{tree.name}</h2>
        <span className="font-mono text-sm text-muted">{pointsInTree(tree, build)}</span>
      </div>
      <div className="space-y-1.5">
        {grid.map((cells, row) => {
          const unlocked = tierUnlocked(tree, build, row);
          return (
            <div key={row} className={clsx("grid grid-cols-4 gap-1.5", !unlocked && "opacity-50")}>
              {cells.map((talent, column) =>
                talent ? (
                  <TalentCell
                    key={talent.id}
                    talent={talent}
                    points={build[talent.id] ?? 0}
                    addable={canAdd(trees, tree, talent, build)}
                    removable={canRemove(tree, talent, build)}
                    onAdd={() => onAdd(talent)}
                    onRemove={() => onRemove(talent)}
                  />
                ) : (
                  <div key={column} />
                ),
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function TalentCell({
  talent,
  points,
  addable,
  removable,
  onAdd,
  onRemove,
}: {
  talent: TalentData;
  points: number;
  addable: boolean;
  removable: boolean;
  onAdd: () => void;
  onRemove: () => void;
}) {
  const spellId =
    talent.rank_spells[Math.max(0, Math.min(points, talent.max_rank) - 1)] ?? talent.rank_spells[0];
  const full = points === talent.max_rank;
  return (
    <div className="flex flex-col items-center gap-0.5">
      <button
        type="button"
        aria-label={`${talent.name} ${points}/${talent.max_rank}`}
        disabled={!addable && !removable}
        onClick={() => addable && onAdd()}
        onContextMenu={(e) => {
          e.preventDefault();
          if (removable) onRemove();
        }}
        className={clsx(
          "relative size-11 rounded border-2 bg-bg transition",
          full
            ? "border-gold"
            : points > 0
              ? "border-success"
              : addable
                ? "border-border hover:border-text"
                : "border-border/50",
          !addable && !removable && "cursor-default",
        )}
      >
        <img
          src={talent.icon_url}
          alt=""
          className={clsx("size-full rounded-sm", points === 0 && !addable && "grayscale")}
        />
        <span
          className={clsx(
            "absolute -right-1 -bottom-1 rounded border bg-bg px-1 font-mono text-[10px] leading-4",
            full
              ? "border-gold text-gold"
              : points > 0
                ? "border-success text-success"
                : "border-border text-muted",
          )}
        >
          {points}/{talent.max_rank}
        </span>
      </button>
      <WowheadLink
        kind="spell"
        id={spellId}
        className="max-w-full truncate text-[10px] text-muted hover:text-text"
      >
        {talent.name}
      </WowheadLink>
    </div>
  );
}
