import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorMessage, type Faction, type GuildSettings } from "@/api/client";
import { GUILD_KEY, useGuild } from "@/api/guild";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Button, Card, Field, Input, PageTitle, Select, Spinner } from "@/components/ui";
import { FACTION_LABELS } from "@/lib/roles";

type Form = Pick<GuildSettings, "name" | "faction" | "realm">;

export function GuildPage() {
  const me = useCurrentUser();
  const guild = useGuild();

  return (
    <>
      <PageTitle>Guilde</PageTitle>
      <Card className="max-w-lg">
        {!guild.data ? (
          <Spinner />
        ) : me.site_role === "gm" ? (
          // `key` réinitialise le formulaire quand les données serveur changent.
          <GuildForm key={guild.data.updated_at} initial={guild.data} />
        ) : (
          <GuildSummary settings={guild.data} />
        )}
      </Card>
    </>
  );
}

function GuildSummary({ settings }: { settings: GuildSettings }) {
  return (
    <>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        <dt className="text-muted">Nom</dt>
        <dd>{settings.name || <em className="text-muted">à décider</em>}</dd>
        <dt className="text-muted">Faction</dt>
        <dd>{FACTION_LABELS[settings.faction ?? ""]}</dd>
        <dt className="text-muted">Royaume</dt>
        <dd>{settings.realm || <em className="text-muted">à choisir</em>}</dd>
      </dl>
      <p className="mt-4 text-xs text-muted">Seul le GM peut modifier ces paramètres.</p>
    </>
  );
}

function GuildForm({ initial }: { initial: GuildSettings }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Form>({
    name: initial.name ?? "",
    faction: initial.faction ?? "",
    realm: initial.realm ?? "",
  });
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const save = useMutation({
    mutationFn: async (body: Form) => {
      const { data, error } = await api.PATCH("/api/guild/", { body });
      if (error || !data) throw error ?? new Error();
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(GUILD_KEY, data);
      setMessage({ kind: "ok", text: "Paramètres enregistrés." });
    },
    onError: (e) => setMessage({ kind: "error", text: errorMessage(e) }),
  });

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(form);
      }}
    >
      <Field label="Nom de la guilde">
        <Input
          value={form.name ?? ""}
          maxLength={24}
          placeholder="À décider par sondage"
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
      </Field>
      <Field label="Faction">
        <Select
          className="w-full"
          value={form.faction ?? ""}
          onChange={(e) => setForm({ ...form, faction: e.target.value as Faction })}
        >
          {(Object.keys(FACTION_LABELS) as Faction[]).map((faction) => (
            <option key={faction} value={faction}>
              {FACTION_LABELS[faction]}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Royaume">
        <Input
          value={form.realm ?? ""}
          maxLength={64}
          onChange={(e) => setForm({ ...form, realm: e.target.value })}
        />
      </Field>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={save.isPending}>
          Enregistrer
        </Button>
        {message && (
          <span className={message.kind === "ok" ? "text-sm text-success" : "text-sm text-danger"}>
            {message.text}
          </span>
        )}
      </div>
    </form>
  );
}
