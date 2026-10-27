import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type ItemIndex } from "@/api/client";
import { unwrap, useGameData } from "@/api/hooks";
import { Card, Input, PageTitle, Select, Spinner } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { SLOT_OPTIONS, formatStats } from "@/lib/items";
import { QUALITY_COLOR, useWowheadTooltips } from "@/lib/wowhead";
import { formatDateTime } from "@/lib/game";

function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export function ItemsPage() {
  const gamedata = useGameData();
  const [query, setQuery] = useState("");
  const [slot, setSlot] = useState("");
  const q = useDebounced(query.trim());

  const items = useQuery({
    queryKey: ["items", q, slot],
    queryFn: () =>
      unwrap(api.GET("/api/items/", { params: { query: { q, slot: slot || undefined, equippable: true } } })),
    enabled: q.length >= 2 || slot !== "",
    placeholderData: (previous) => previous,
  });
  useWowheadTooltips([items.data]);

  const run = gamedata.data?.import_run as { build?: string; imported_at?: string } | null | undefined;

  return (
    <>
      <PageTitle>Objets</PageTitle>
      <Card className="mb-4 flex flex-wrap items-end gap-3">
        <label className="flex-1 text-sm">
          <span className="text-muted">Nom (français ou anglais)</span>
          <Input
            value={query}
            placeholder="Ex. Lame-tonnerre, Thunderfury…"
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        </label>
        <label className="text-sm">
          <span className="text-muted">Emplacement</span>
          <Select className="block w-full" value={slot} onChange={(e) => setSlot(e.target.value)}>
            {SLOT_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </label>
      </Card>

      {!items.data && !items.isFetching && (
        <p className="text-sm text-muted">
          Tape au moins deux lettres ou choisis un emplacement. Survole un objet pour l'infobulle Wowhead.
        </p>
      )}
      {items.isFetching && !items.data && <Spinner />}
      {items.data && (
        <Card className="p-0">
          {items.data.length === 0 ? (
            <p className="p-6 text-center text-sm text-muted">
              Aucun objet. Si c'est une nouveauté WoW Forever, le GM peut l'ajouter dans l'admin.
            </p>
          ) : (
            <ul className="divide-y divide-border/60">
              {items.data.map((item) => (
                <ItemRow key={item.id} item={item} />
              ))}
            </ul>
          )}
        </Card>
      )}
      {run?.build && (
        <p className="mt-4 text-xs text-muted">
          Index importé depuis le client {run.build}
          {run.imported_at && ` le ${formatDateTime(run.imported_at)}`}. Infobulles et fiches détaillées :
          Wowhead.
        </p>
      )}
    </>
  );
}

function ItemRow({ item }: { item: ItemIndex }) {
  return (
    <li className="flex items-center gap-3 px-3 py-2 text-sm">
      <img src={item.icon_url} alt="" className="size-9 rounded border border-border" loading="lazy" />
      <div className="min-w-0 flex-1">
        <WowheadLink kind="item" id={item.id} quality={item.quality} className="font-medium hover:underline">
          {item.name}
        </WowheadLink>
        <div className="truncate text-xs text-muted">
          {item.name_en && item.name_en !== item.name && <span>{item.name_en} · </span>}
          {formatStats(item.stats as Record<string, number> | undefined)}
        </div>
      </div>
      <div className="text-right text-xs text-muted">
        <div style={{ color: QUALITY_COLOR[item.quality ?? 1] }}>ilvl {item.item_level}</div>
        {item.required_level ? <div>niveau {item.required_level}</div> : null}
        {item.is_unique && <div>unique</div>}
      </div>
    </li>
  );
}
