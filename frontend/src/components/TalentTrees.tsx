import clsx from "clsx";
import { Card } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import {
  COLUMNS,
  type Build,
  type TalentData,
  type TalentTreeData,
  canAdd,
  canRemove,
  pointsInTree,
  tierUnlocked,
} from "@/lib/talents";

interface Props {
  trees: TalentTreeData[];
  build: Build;
  /** Points acquis par talent (sous-ensemble de `build`) ; absent = tout est acquis. */
  acquired?: Build;
  readOnly?: boolean;
  onAdd: (talent: TalentData) => void;
  onRemove: (talent: TalentData) => void;
}

/** Les trois arbres d'une classe, cliquables. */
export function TalentTrees({ trees, build, acquired, readOnly, onAdd, onRemove }: Props) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {trees.map((tree) => (
        <TreeCard
          key={tree.id}
          tree={tree}
          trees={trees}
          build={build}
          acquired={acquired}
          readOnly={readOnly}
          onAdd={onAdd}
          onRemove={onRemove}
        />
      ))}
    </div>
  );
}

function TreeCard({
  tree,
  trees,
  build,
  acquired,
  readOnly,
  onAdd,
  onRemove,
}: Props & { tree: TalentTreeData }) {
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
                    acquiredPoints={acquired ? (acquired[talent.id] ?? 0) : (build[talent.id] ?? 0)}
                    addable={!readOnly && canAdd(trees, tree, talent, build)}
                    removable={!readOnly && canRemove(tree, talent, build)}
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
  acquiredPoints,
  addable,
  removable,
  onAdd,
  onRemove,
}: {
  talent: TalentData;
  points: number;
  acquiredPoints: number;
  addable: boolean;
  removable: boolean;
  onAdd: () => void;
  onRemove: () => void;
}) {
  const spellId =
    talent.rank_spells[Math.max(0, Math.min(points, talent.max_rank) - 1)] ?? talent.rank_spells[0];
  const full = points === talent.max_rank;
  const projected = points > acquiredPoints;
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
          projected
            ? "border-dashed border-muted"
            : full
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
            projected
              ? "border-muted text-muted"
              : full
                ? "border-gold text-gold"
                : points > 0
                  ? "border-success text-success"
                  : "border-border text-muted",
          )}
          title={projected ? `${acquiredPoints} acquis, ${points - acquiredPoints} projeté(s)` : undefined}
        >
          {projected ? `${acquiredPoints}+${points - acquiredPoints}` : points}/{talent.max_rank}
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
