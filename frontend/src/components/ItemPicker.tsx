import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type EnchantmentIndex, type ItemIndex } from "@/api/client";
import { unwrap } from "@/api/hooks";
import { Button, Input, Spinner } from "@/components/ui";
import { formatStats } from "@/lib/items";
import { QUALITY_COLOR } from "@/lib/wowhead";

interface Props {
  slotLabel: string;
  slotFilter: string;
  /** Emplacement API (`head`, `finger`…) pour filtrer les enchantements. */
  enchantSlot: string;
  current: { item: ItemIndex | null; enchantment: EnchantmentIndex | null };
  onChoose: (item: ItemIndex | null, enchantment: EnchantmentIndex | null) => void;
  onClose: () => void;
}

/** Boîte de choix d'un objet (recherche) et d'un enchantement pour un emplacement. */
export function ItemPicker({ slotLabel, slotFilter, enchantSlot, current, onChoose, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [item, setItem] = useState<ItemIndex | null>(current.item);
  const [enchantment, setEnchantment] = useState<EnchantmentIndex | null>(current.enchantment);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), 250);
    return () => window.clearTimeout(id);
  }, [query]);

  const items = useQuery({
    queryKey: ["items", debounced, slotFilter],
    queryFn: () =>
      unwrap(
        api.GET("/api/items/", { params: { query: { q: debounced, slot: slotFilter, equippable: true } } }),
      ),
    placeholderData: (previous) => previous,
  });
  const enchants = useQuery({
    queryKey: ["enchantments", enchantSlot],
    queryFn: () => unwrap(api.GET("/api/enchantments/", { params: { query: { slot: enchantSlot } } })),
    staleTime: Infinity,
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border border-border bg-surface"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-border p-3">
          <h3 className="font-display text-lg">{slotLabel}</h3>
          <Input
            value={query}
            autoFocus
            placeholder="Rechercher un objet (FR ou EN)…"
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1"
          />
          <Button variant="ghost" onClick={onClose} aria-label="Fermer">
            ✕
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {items.isPending ? (
            <div className="p-6">
              <Spinner />
            </div>
          ) : (
            <ul className="divide-y divide-border/60">
              {items.data?.map((candidate) => (
                <li key={candidate.id}>
                  <button
                    type="button"
                    onClick={() => setItem(candidate)}
                    className={
                      item?.id === candidate.id
                        ? "flex w-full items-center gap-3 bg-gold/10 px-3 py-2 text-left text-sm"
                        : "flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-surface-2"
                    }
                  >
                    <img
                      src={candidate.icon_url}
                      alt=""
                      className="size-8 rounded border border-border"
                      loading="lazy"
                    />
                    <span className="min-w-0 flex-1">
                      <span
                        className="block truncate font-medium"
                        style={{ color: QUALITY_COLOR[candidate.quality ?? 1] }}
                      >
                        {candidate.name}
                      </span>
                      <span className="block truncate text-xs text-muted">
                        {formatStats(candidate.stats as Record<string, number>)}
                      </span>
                    </span>
                    <span className="text-right text-xs text-muted">
                      ilvl {candidate.item_level}
                      {candidate.required_level ? (
                        <span className="block">niv. {candidate.required_level}</span>
                      ) : null}
                    </span>
                  </button>
                </li>
              ))}
              {items.data?.length === 0 && (
                <li className="p-6 text-center text-sm text-muted">Aucun objet.</li>
              )}
            </ul>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-border p-3 text-sm">
          <label className="flex flex-1 items-center gap-2">
            <span className="text-muted">Enchantement</span>
            <select
              value={enchantment?.id ?? ""}
              disabled={!item}
              onChange={(e) =>
                setEnchantment(enchants.data?.find((x) => x.id === Number(e.target.value)) ?? null)
              }
              className="min-w-0 flex-1 rounded-md border border-border bg-bg px-2 py-1.5 text-sm"
            >
              <option value="">Aucun</option>
              {enchants.data?.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </select>
          </label>
          {current.item && (
            <Button variant="danger" onClick={() => onChoose(null, null)}>
              Vider
            </Button>
          )}
          <Button disabled={!item} onClick={() => onChoose(item, item ? enchantment : null)}>
            Équiper
          </Button>
        </div>
      </div>
    </div>
  );
}
