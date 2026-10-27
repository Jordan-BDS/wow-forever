import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorMessage } from "@/api/client";
import { KEYS, useInvalidate, useMyAvailability } from "@/api/hooks";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { ME_KEY } from "@/auth/useMe";
import { AvailabilityGrid } from "@/components/AvailabilityGrid";
import { Button, Card, Field, Input, PageTitle, Spinner } from "@/components/ui";
import { cellsToSlots, slotsToCells } from "@/lib/availability";

export function ProfilePage() {
  const me = useCurrentUser();
  const availability = useMyAvailability();
  if (availability.isPending) return <Spinner />;
  return (
    <>
      <PageTitle>Mon profil</PageTitle>
      <div className="grid gap-4 md:grid-cols-[360px_1fr]">
        <ProfileForm key={me.id} initialName={me.display_name} initialBio={me.bio ?? ""} />
        <AvailabilityEditor
          key={JSON.stringify(availability.data)}
          initial={slotsToCells(availability.data ?? [])}
        />
      </div>
    </>
  );
}

function ProfileForm({ initialName, initialBio }: { initialName: string; initialBio: string }) {
  const invalidate = useInvalidate();
  const [displayName, setDisplayName] = useState(initialName);
  const [bio, setBio] = useState(initialBio);
  const [message, setMessage] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      const { error } = await api.PATCH("/api/auth/me/", { body: { display_name: displayName.trim(), bio } });
      if (error) throw error;
    },
    onSuccess: async () => {
      await invalidate(ME_KEY, KEYS.members, KEYS.characters);
      setMessage("Profil enregistré.");
    },
    onError: (e) => setMessage(errorMessage(e)),
  });

  return (
    <Card>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <h2 className="font-display text-lg">Identité</h2>
        <Field label="Nom affiché">
          <Input
            value={displayName}
            minLength={2}
            maxLength={64}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </Field>
        <Field label="Bio">
          <textarea
            value={bio}
            rows={4}
            onChange={(e) => setBio(e.target.value)}
            className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm focus:border-gold focus:outline-none"
          />
        </Field>
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={save.isPending}>
            Enregistrer
          </Button>
          {message && <span className="text-sm text-muted">{message}</span>}
        </div>
      </form>
    </Card>
  );
}

function AvailabilityEditor({ initial }: { initial: Set<string> }) {
  const invalidate = useInvalidate();
  const [cells, setCells] = useState(initial);
  const [message, setMessage] = useState<string | null>(null);
  const dirty = JSON.stringify([...cells].sort()) !== JSON.stringify([...initial].sort());

  const save = useMutation({
    mutationFn: async () => {
      const { error } = await api.PUT("/api/auth/me/availability/", { body: cellsToSlots(cells) });
      if (error) throw error;
    },
    onSuccess: async () => {
      await invalidate(KEYS.myAvailability, KEYS.guildAvailability);
      setMessage("Disponibilités enregistrées.");
    },
    onError: (e) => setMessage(errorMessage(e)),
  });

  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-display text-lg">Mes disponibilités</h2>
          <p className="text-xs text-muted">Clique sur les heures où tu joues en général (heure de Paris).</p>
        </div>
        <div className="flex items-center gap-3">
          {message && !dirty && <span className="text-sm text-muted">{message}</span>}
          <Button disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            Enregistrer
          </Button>
        </div>
      </div>
      <AvailabilityGrid
        mode="edit"
        cells={cells}
        onToggle={(key) => {
          setMessage(null);
          setCells((prev) => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
          });
        }}
      />
    </Card>
  );
}
