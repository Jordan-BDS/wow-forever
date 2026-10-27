import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import {
  api,
  errorMessage,
  type Character,
  type EnchantmentIndex,
  type EquipmentSet,
  type ItemIndex,
  type SlotKey,
} from "@/api/client";
import { KEYS, unwrap, useInvalidate } from "@/api/hooks";
import { ItemPicker } from "@/components/ItemPicker";
import { Button, Card, Input } from "@/components/ui";
import { WowheadLink } from "@/components/wowhead";
import { SHEET_SLOTS, STAT_LABEL } from "@/lib/items";
import { useWowheadTooltips } from "@/lib/wowhead";

interface Props {
  character: Character;
  sets: EquipmentSet[];
  canEdit: boolean;
}

type SlotState = Record<string, { item: ItemIndex | null; enchantment: EnchantmentIndex | null }>;

function slotsOf(set: EquipmentSet | undefined): SlotState {
  const state: SlotState = {};
  for (const slot of set?.slots ?? []) {
    state[slot.slot] = {
      item: slot.item as ItemIndex,
      enchantment: (slot.enchantment as EnchantmentIndex) ?? null,
    };
  }
  return state;
}

export function EquipmentPanel({ character, sets, canEdit }: Props) {
  const invalidate = useInvalidate();
  const [selectedId, setSelectedId] = useState<number | null>(
    sets.find((s) => s.is_primary)?.id ?? sets[0]?.id ?? null,
  );
  const selected = sets.find((s) => s.id === selectedId) ?? sets.find((s) => s.is_primary) ?? sets[0];
  const [picking, setPicking] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const slots = slotsOf(selected);
  useWowheadTooltips([selected?.updated_at]);

  const stats = useQuery({
    queryKey: ["equipment-stats", character.id, selected?.id, selected?.updated_at, character.level],
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_pk}/equipment-sets/{id}/stats/", {
          params: { path: { character_pk: character.id, id: String(selected!.id) } },
        }),
      ),
    enabled: !!selected,
  });

  const refresh = () => invalidate(KEYS.equipmentSets(character.id));
  const base = { params: { path: { character_pk: character.id, id: String(selected?.id ?? 0) } } };

  const saveSlots = useMutation({
    mutationFn: async (next: SlotState) => {
      const { error } = await api.PUT("/api/characters/{character_pk}/equipment-sets/{id}/slots/", {
        ...base,
        body: {
          slots: Object.entries(next)
            .filter(([, v]) => v.item)
            .map(([slot, v]) => ({
              slot: slot as SlotKey,
              item: v.item!.id,
              enchantment: v.enchantment?.id ?? null,
            })),
        },
      });
      if (error) throw error;
    },
    onSuccess: () => {
      setError(null);
      return refresh();
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const create = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/characters/{character_pk}/equipment-sets/", {
        params: { path: { character_pk: character.id } },
        body: { name: sets.length === 0 ? "Principal" : `Set ${sets.length + 1}` },
      });
      if (error || !data) throw error ?? new Error();
      return data;
    },
    onSuccess: async (set) => {
      await refresh();
      setSelectedId(set.id);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const action = useMutation({
    mutationFn: async ({
      kind,
      name,
    }: {
      kind: "primary" | "duplicate" | "rename" | "delete";
      name?: string;
    }) => {
      if (!selected) return null;
      if (kind === "primary") {
        const { error } = await api.POST(
          "/api/characters/{character_pk}/equipment-sets/{id}/set-primary/",
          base,
        );
        if (error) throw error;
      } else if (kind === "duplicate") {
        const { data, error } = await api.POST(
          "/api/characters/{character_pk}/equipment-sets/{id}/duplicate/",
          base,
        );
        if (error || !data) throw error ?? new Error();
        return data.id;
      } else if (kind === "rename") {
        const { error } = await api.PATCH("/api/characters/{character_pk}/equipment-sets/{id}/", {
          ...base,
          body: { name },
        });
        if (error) throw error;
      } else {
        const { error } = await api.DELETE("/api/characters/{character_pk}/equipment-sets/{id}/", base);
        if (error) throw error;
        setSelectedId(null);
      }
      return null;
    },
    onSuccess: async (newId) => {
      setRenaming(null);
      await refresh();
      if (newId) setSelectedId(newId);
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const pickingSlot = SHEET_SLOTS.find((s) => s.key === picking);

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-2 text-sm">
        {sets.length === 0 && <span className="text-muted">Aucun set d'équipement pour l'instant.</span>}
        {sets.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSelectedId(s.id)}
            className={
              s.id === selected?.id
                ? "rounded-md border border-gold bg-gold/10 px-3 py-1 text-gold"
                : "rounded-md border border-border px-3 py-1 text-muted hover:text-text"
            }
          >
            {s.name}
            {s.is_primary && " ★"}
          </button>
        ))}
        {canEdit && (
          <Button variant="ghost" disabled={create.isPending} onClick={() => create.mutate()}>
            + Nouveau set
          </Button>
        )}
        {canEdit && selected && (
          <span className="ml-auto flex flex-wrap gap-2">
            {!selected.is_primary && (
              <Button variant="ghost" onClick={() => action.mutate({ kind: "primary" })}>
                Principal
              </Button>
            )}
            <Button variant="ghost" onClick={() => action.mutate({ kind: "duplicate" })}>
              Dupliquer
            </Button>
            {renaming === null && (
              <Button variant="ghost" onClick={() => setRenaming(selected.name)}>
                Renommer
              </Button>
            )}
            <Button
              variant="danger"
              onClick={() => {
                if (window.confirm(`Supprimer le set « ${selected.name} » ?`))
                  action.mutate({ kind: "delete" });
              }}
            >
              Supprimer
            </Button>
          </span>
        )}
        {renaming !== null && (
          <form
            className="flex w-full items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              action.mutate({ kind: "rename", name: renaming.trim() });
            }}
          >
            <Input
              value={renaming}
              maxLength={40}
              autoFocus
              onChange={(e) => setRenaming(e.target.value)}
              className="max-w-xs"
            />
            <Button type="submit">OK</Button>
            <Button type="button" variant="ghost" onClick={() => setRenaming(null)}>
              Annuler
            </Button>
          </form>
        )}
      </Card>
      {error && <p className="text-sm text-danger">{error}</p>}

      {selected && (
        <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
          <Card className="p-3">
            <div className="grid gap-1.5 sm:grid-cols-2">
              {SHEET_SLOTS.map((slot) => {
                const entry = slots[slot.key];
                const projected =
                  !!entry?.item?.required_level && entry.item.required_level > (character.level ?? 1);
                return (
                  <button
                    key={slot.key}
                    type="button"
                    disabled={!canEdit}
                    onClick={() => setPicking(slot.key)}
                    className={clsx(
                      "flex items-center gap-2 rounded-md border px-2 py-1.5 text-left text-sm transition",
                      projected ? "border-dashed border-muted" : "border-border",
                      canEdit ? "hover:border-gold/60" : "cursor-default",
                    )}
                    title={projected ? `Projeté : niveau ${entry!.item!.required_level} requis` : undefined}
                  >
                    {entry?.item ? (
                      <img
                        src={entry.item.icon_url}
                        alt=""
                        className={clsx("size-9 rounded border border-border", projected && "opacity-60")}
                      />
                    ) : (
                      <span className="flex size-9 items-center justify-center rounded border border-dashed border-border text-xs text-muted">
                        +
                      </span>
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="block text-[10px] uppercase text-muted">
                        {slot.label}
                        {projected && " · projeté"}
                      </span>
                      {entry?.item ? (
                        <WowheadLink
                          kind="item"
                          id={entry.item.id}
                          quality={entry.item.quality}
                          className="block truncate font-medium"
                        >
                          {entry.item.name}
                        </WowheadLink>
                      ) : (
                        <span className="block text-muted">—</span>
                      )}
                      {entry?.enchantment && (
                        <span className="block truncate text-xs text-success">{entry.enchantment.name}</span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          </Card>

          <Card className="text-sm">
            <h3 className="mb-2 font-display text-lg">Statistiques</h3>
            {stats.data ? (
              <>
                {Object.keys(stats.data.totals).length === 0 ? (
                  <p className="text-muted">Rien d'acquis à additionner.</p>
                ) : (
                  <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1">
                    {Object.entries(stats.data.totals).map(([stat, value]) => {
                      const parts = stats.data!.breakdown[stat] ?? {};
                      const detail = Object.entries(parts)
                        .map(([src, v]) => `${src === "items" ? "objets" : "enchantements"} ${v}`)
                        .join(", ");
                      return (
                        <div key={stat} className="contents">
                          <dt className="text-muted" title={detail}>
                            {STAT_LABEL[stat] ?? stat}
                          </dt>
                          <dd className="text-right font-mono" title={detail}>
                            {value}
                          </dd>
                        </div>
                      );
                    })}
                  </dl>
                )}
                {stats.data.projected_slots.length > 0 && (
                  <p className="mt-2 text-xs text-muted">
                    {stats.data.projected_slots.length} objet(s) projeté(s) exclu(s) du calcul.
                  </p>
                )}
                {(stats.data.active_set_bonuses.length > 0 || stats.data.inactive_set_bonuses.length > 0) && (
                  <div className="mt-3 border-t border-border pt-2">
                    <p className="text-xs uppercase text-muted">Bonus de set</p>
                    <ul className="mt-1 space-y-1 text-xs">
                      {[...stats.data.active_set_bonuses, ...stats.data.inactive_set_bonuses].map(
                        (bonus, i) => {
                          const active = i < stats.data!.active_set_bonuses.length;
                          return (
                            <li key={i} className={active ? "text-success" : "text-muted"}>
                              {String(bonus.set)} ({String(bonus.threshold)}) :{" "}
                              <WowheadLink
                                kind="spell"
                                id={Number(bonus.spell_id)}
                                className={active ? "text-success" : "text-muted"}
                              >
                                {bonusLabel(bonus)}
                              </WowheadLink>
                            </li>
                          );
                        },
                      )}
                    </ul>
                  </div>
                )}
                <p className="mt-3 text-xs text-muted">
                  Somme des stats brutes (objets, enchantements). Les stats dérivées viendront plus tard.
                </p>
              </>
            ) : (
              <p className="text-muted">Calcul…</p>
            )}
          </Card>
        </div>
      )}

      {pickingSlot && selected && (
        <ItemPicker
          slotLabel={pickingSlot.label}
          slotFilter={pickingSlot.filter}
          enchantSlot={pickingSlot.filter.split(",")[0]}
          current={slots[pickingSlot.key] ?? { item: null, enchantment: null }}
          onChoose={(item, enchantment) => {
            setPicking(null);
            saveSlots.mutate({ ...slots, [pickingSlot.key]: { item, enchantment } });
          }}
          onClose={() => setPicking(null)}
        />
      )}
    </div>
  );
}

/** Les descriptions du client contiennent des variables ($s1…) : on affiche un libellé neutre dans ce cas. */
function bonusLabel(bonus: Record<string, unknown>): string {
  const description = String(bonus.description ?? "");
  if (!description || description.includes("$"))
    return `bonus ${String(bonus.threshold)} pièces (détail Wowhead)`;
  return description.slice(0, 80);
}
