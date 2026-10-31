import clsx from "clsx";
import { GRID_HOURS, cellKey } from "@/lib/availability";
import { WEEKDAYS_SHORT } from "@/lib/game";

interface EditableProps {
  mode: "edit";
  cells: Set<string>;
  onToggle: (key: string) => void;
}

interface HeatmapProps {
  mode: "heatmap";
  names: Map<string, string[]>;
  total: number;
}

type Props = EditableProps | HeatmapProps;

/** Grille jour × heure, cliquable (mes dispos) ou en chaleur (dispos de la guilde). */
export function AvailabilityGrid(props: Props) {
  return (
    <div className="nav-scroll -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <table className="w-full min-w-[520px] table-fixed border-separate border-spacing-0.5 text-xs">
        <thead>
          <tr>
            <th className="w-12" />
            {WEEKDAYS_SHORT.map((day) => (
              <th key={day} className="py-1 font-medium text-muted">
                {day}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {GRID_HOURS.map((hour) => (
            <tr key={hour}>
              <th className="pr-2 text-right font-mono font-normal text-muted">{hour}h</th>
              {WEEKDAYS_SHORT.map((_, weekday) => {
                const key = cellKey(weekday, hour);
                if (props.mode === "edit") {
                  const on = props.cells.has(key);
                  return (
                    <td key={key} className="p-0">
                      <button
                        type="button"
                        aria-pressed={on}
                        aria-label={`${WEEKDAYS_SHORT[weekday]} ${hour}h`}
                        onClick={() => props.onToggle(key)}
                        className={clsx(
                          "h-6 w-full rounded-sm border transition",
                          on ? "border-success bg-success/70" : "border-border bg-surface-2 hover:bg-border",
                        )}
                      />
                    </td>
                  );
                }
                const names = props.names.get(key) ?? [];
                const ratio = props.total ? names.length / props.total : 0;
                return (
                  <td key={key} className="p-0">
                    <div
                      title={names.length ? names.join(", ") : "Personne"}
                      className="flex h-6 items-center justify-center rounded-sm border border-border text-[10px]"
                      style={{ background: `rgba(95, 168, 104, ${ratio * 0.85})` }}
                    >
                      {names.length > 0 && names.length}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
