import type { AvailabilitySlot } from "@/api/client";

/** Heures affichées dans les grilles (8 h → minuit). */
export const GRID_HOURS = Array.from({ length: 16 }, (_, i) => i + 8);

export const cellKey = (weekday: number, hour: number) => `${weekday}-${hour}`;

/** Créneaux → ensemble de cellules « jour-heure ». */
export function slotsToCells(
  slots: { weekday: number; start_hour: number; end_hour: number }[],
): Set<string> {
  const cells = new Set<string>();
  for (const slot of slots) {
    for (let hour = slot.start_hour; hour < slot.end_hour; hour++) cells.add(cellKey(slot.weekday, hour));
  }
  return cells;
}

/** Cellules → créneaux contigus, triés par jour puis heure. */
export function cellsToSlots(cells: Set<string>): AvailabilitySlot[] {
  const slots: AvailabilitySlot[] = [];
  for (let weekday = 0; weekday < 7; weekday++) {
    let start: number | null = null;
    for (let hour = 0; hour <= 24; hour++) {
      const on = hour < 24 && cells.has(cellKey(weekday, hour));
      if (on && start === null) start = hour;
      if (!on && start !== null) {
        slots.push({ weekday: weekday as AvailabilitySlot["weekday"], start_hour: start, end_hour: hour });
        start = null;
      }
    }
  }
  return slots;
}

/** Pour la vue guilde : noms disponibles par cellule. */
export function namesByCell(
  slots: { weekday: number; start_hour: number; end_hour: number; display_name: string }[],
) {
  const map = new Map<string, string[]>();
  for (const slot of slots) {
    for (let hour = slot.start_hour; hour < slot.end_hour; hour++) {
      const key = cellKey(slot.weekday, hour);
      map.set(key, [...(map.get(key) ?? []), slot.display_name]);
    }
  }
  return map;
}
