import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate } from "react-router";
import { api, errorMessage, fieldErrors, type Faction, type GuildSettings } from "@/api/client";
import { GUILD_KEY, useGuild } from "@/api/guild";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Button, Card, Field, Input, PageTitle, Select, Spinner, Textarea } from "@/components/ui";
import { FACTION_LABELS } from "@/lib/roles";

/** Paramètres de la guilde : réservés au GM. */
export function GuildPage() {
  const me = useCurrentUser();
  const guild = useGuild();
  if (me.site_role !== "gm") return <Navigate to="/roster" replace />;
  if (!guild.data) return <Spinner />;
  return (
    <>
      <PageTitle>Paramètres de la guilde</PageTitle>
      <GuildForm key={guild.data.updated_at} initial={guild.data} />
    </>
  );
}

type Form = {
  name: string;
  faction: Faction;
  realm: string;
  values: string;
  discord_channel_id: string;
  discord_agenda_channel_id: string;
  discord_crafts_channel_id: string;
  discord_polls_channel_id: string;
  reminder_minutes: number;
  accepted_interface_versions: string;
  discord_client_id: string;
  discord_client_secret: string;
  discord_bot_token: string;
  discord_guild_id: string;
  discord_allowed_role_ids: string;
  discord_first_gm_id: string;
};

type Check = {
  ok: boolean;
  detail: string;
  guild_name: string;
  roles: { id: string; name: string; allowed: boolean }[];
  channels: { id: string; name: string; category: string }[];
};

type ChannelField =
  | "discord_agenda_channel_id"
  | "discord_crafts_channel_id"
  | "discord_polls_channel_id"
  | "discord_channel_id";

const CHANNEL_FIELDS: { field: ChannelField; label: string; hint: string }[] = [
  {
    field: "discord_agenda_channel_id",
    label: "Agenda",
    hint: "Messages d'inscription à boutons, déplacements, annulations, rappels, compositions",
  },
  { field: "discord_crafts_channel_id", label: "Demandes de craft", hint: "Nouvelles demandes" },
  { field: "discord_polls_channel_id", label: "Sondages", hint: "Ouverture, rappels, résultat" },
  {
    field: "discord_channel_id",
    label: "Général (secours)",
    hint: "Reçoit les annonces dont le salon dédié n'est pas renseigné",
  },
];

function GuildForm({ initial }: { initial: GuildSettings }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Form>({
    name: initial.name ?? "",
    faction: initial.faction ?? "",
    realm: initial.realm ?? "",
    values: initial.values ?? "",
    discord_channel_id: initial.discord_channel_id ?? "",
    discord_agenda_channel_id: initial.discord_agenda_channel_id ?? "",
    discord_crafts_channel_id: initial.discord_crafts_channel_id ?? "",
    discord_polls_channel_id: initial.discord_polls_channel_id ?? "",
    reminder_minutes: initial.reminder_minutes ?? 60,
    accepted_interface_versions: initial.accepted_interface_versions ?? "",
    discord_client_id: initial.discord_client_id ?? "",
    discord_client_secret: "",
    discord_bot_token: "",
    discord_guild_id: initial.discord_guild_id ?? "",
    discord_allowed_role_ids: initial.discord_allowed_role_ids ?? "",
    discord_first_gm_id: initial.discord_first_gm_id ?? "",
  });
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [check, setCheck] = useState<Check | null>(null);

  const save = useMutation({
    mutationFn: async (body: Form) => {
      const { data, error } = await api.PATCH("/api/guild/", { body });
      if (error || !data) throw error ?? new Error();
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(GUILD_KEY, data);
      setErrors({});
      setMessage({ kind: "ok", text: "Paramètres enregistrés." });
    },
    onError: (e) => {
      setErrors(fieldErrors(e));
      setMessage({ kind: "error", text: errorMessage(e) });
    },
  });

  const verify = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/guild/discord-check/");
      if (error || !data) throw error ?? new Error();
      return data as Check;
    },
    onSuccess: setCheck,
    onError: (e) => setCheck({ ok: false, detail: errorMessage(e), guild_name: "", roles: [], channels: [] }),
  });

  const update = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));
  const Err = (field: keyof Form) =>
    errors[field] ? <p className="text-xs text-danger">{errors[field]}</p> : null;

  return (
    <form
      className="grid gap-4 lg:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(form);
      }}
    >
      <Card className="space-y-4">
        <h2 className="font-display text-lg">Jeu</h2>
        <Field label="Nom de la guilde">
          <Input
            value={form.name}
            maxLength={24}
            placeholder="À décider par sondage"
            onChange={(e) => update({ name: e.target.value })}
          />
        </Field>
        <Field label="Faction">
          <Select
            className="w-full"
            value={form.faction}
            onChange={(e) => update({ faction: e.target.value as Faction })}
          >
            {(Object.keys(FACTION_LABELS) as Faction[]).map((faction) => (
              <option key={faction} value={faction}>
                {FACTION_LABELS[faction]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Royaume">
          <Input value={form.realm} maxLength={64} onChange={(e) => update({ realm: e.target.value })} />
        </Field>
        <Field label="Versions d'interface acceptées à l'import">
          <Input
            value={form.accepted_interface_versions}
            maxLength={64}
            onChange={(e) => update({ accepted_interface_versions: e.target.value })}
          />
          <p className="text-xs text-muted">
            Numéro renvoyé par le client de jeu (WoW Forever : 16001). Les exports d'un autre client (Retail,
            Classic) sont refusés. Vide : tout accepter, utile pour les tests.
          </p>
          {Err("accepted_interface_versions")}
        </Field>
        <Field label="Valeurs de la guilde (affichées en citation sur l'accueil)">
          <Textarea
            rows={12}
            maxLength={1000}
            value={form.values}
            placeholder={
              "Entraide avant tout, zéro prise de tête.\n\nLes retours à la ligne sont conservés, une ligne vide sépare les strophes."
            }
            onChange={(e) => update({ values: e.target.value })}
          />
          {Err("values")}
        </Field>
      </Card>

      <Card className="space-y-4">
        <h2 className="font-display text-lg">Salons du bot</h2>
        {CHANNEL_FIELDS.map(({ field, label, hint }) => (
          <Field key={field} label={label}>
            {check && check.channels.length > 0 ? (
              <Select
                className="w-full"
                value={form[field]}
                onChange={(e) => update({ [field]: e.target.value } as Partial<Form>)}
              >
                <option value="">— aucun —</option>
                {check.channels.map((channel) => (
                  <option key={channel.id} value={channel.id}>
                    #{channel.name}
                    {channel.category && ` (${channel.category})`}
                  </option>
                ))}
                {form[field] && !check.channels.some((c) => c.id === form[field]) && (
                  <option value={form[field]}>ID {form[field]} (salon introuvable)</option>
                )}
              </Select>
            ) : (
              <Input
                value={form[field]}
                maxLength={32}
                inputMode="numeric"
                placeholder="ID du salon, ou « Vérifier le serveur » pour choisir dans une liste"
                onChange={(e) => update({ [field]: e.target.value.trim() } as Partial<Form>)}
              />
            )}
            <p className="text-xs text-muted">{hint}</p>
            {Err(field)}
          </Field>
        ))}
        <Field label="Rappel avant un événement (minutes, 0 = aucun)">
          <Input
            type="number"
            min={0}
            max={1440}
            value={form.reminder_minutes}
            onChange={(e) => update({ reminder_minutes: Number(e.target.value) })}
          />
        </Field>
        <p className="text-xs text-muted">
          Les salons agenda et demande-de-craft se créent en lecture seule (réactions et boutons autorisés)
          avec la commande <code className="rounded bg-bg px-1">discord_setup_channels</code>, qui les
          enregistre ici. Clique « Vérifier le serveur » ci-dessous pour choisir les salons dans une liste.
        </p>
      </Card>

      <Card className="space-y-4 lg:col-span-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-lg">Connexion Discord</h2>
          <span className={initial.discord_login_ready ? "text-sm text-success" : "text-sm text-danger"}>
            {initial.discord_login_ready
              ? "Connexion prête"
              : "Connexion incomplète : les membres ne peuvent pas entrer"}
          </span>
        </div>
        <p className="text-sm text-muted">
          Depuis le portail développeur Discord, crée une application : l'onglet OAuth2 donne le Client ID et
          le secret, l'onglet Bot donne le token. Ajoute l'URL de retour{" "}
          <code className="rounded bg-bg px-1 break-all">{`${window.location.origin.replace(":3001", ":8001")}/api/auth/discord/callback/`}</code>{" "}
          dans « Redirects », puis invite le bot sur le serveur. Les identifiants se copient dans Discord avec
          le mode développeur.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Client ID de l'application">
            <Input
              value={form.discord_client_id}
              inputMode="numeric"
              onChange={(e) => update({ discord_client_id: e.target.value.trim() })}
            />
            {Err("discord_client_id")}
          </Field>
          <Field
            label={
              initial.discord_client_secret_set
                ? "Client secret (défini, laisser vide pour conserver)"
                : "Client secret"
            }
          >
            <Input
              type="password"
              autoComplete="off"
              value={form.discord_client_secret}
              onChange={(e) => update({ discord_client_secret: e.target.value.trim() })}
            />
          </Field>
          <Field
            label={
              initial.discord_bot_token_set
                ? "Token du bot (défini, laisser vide pour conserver)"
                : "Token du bot"
            }
          >
            <Input
              type="password"
              autoComplete="off"
              value={form.discord_bot_token}
              onChange={(e) => update({ discord_bot_token: e.target.value.trim() })}
            />
          </Field>
          <Field label="ID du serveur Discord">
            <Input
              value={form.discord_guild_id}
              inputMode="numeric"
              onChange={(e) => update({ discord_guild_id: e.target.value.trim() })}
            />
            {Err("discord_guild_id")}
          </Field>
          <Field label="IDs des rôles autorisés à se connecter (séparés par des virgules)">
            <Input
              value={form.discord_allowed_role_ids}
              onChange={(e) => update({ discord_allowed_role_ids: e.target.value })}
            />
            {Err("discord_allowed_role_ids")}
          </Field>
          <Field label="ID Discord du premier GM (promu à sa première connexion)">
            <Input
              value={form.discord_first_gm_id}
              inputMode="numeric"
              onChange={(e) => update({ discord_first_gm_id: e.target.value.trim() })}
            />
            {Err("discord_first_gm_id")}
          </Field>
        </div>
        <p className="text-xs text-muted">
          Les rôles Discord servent uniquement à autoriser l'entrée. Les rôles du site (GM, Officier, Membre)
          se gèrent dans Membres.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" variant="ghost" disabled={verify.isPending} onClick={() => verify.mutate()}>
            Vérifier le serveur, les rôles et les salons
          </Button>
          <span className="text-xs text-muted">Utilise les valeurs enregistrées : enregistre d'abord.</span>
        </div>
        {check && (
          <div
            className={
              check.ok
                ? "rounded-sm border border-success/50 p-3 text-sm"
                : "rounded-sm border border-danger/50 p-3 text-sm"
            }
          >
            <p className={check.ok ? "text-success" : "text-danger"}>{check.detail}</p>
            {check.roles.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-2">
                {check.roles.map((role) => (
                  <li
                    key={role.id}
                    className={
                      role.allowed
                        ? "rounded-sm border border-gold/60 px-2 py-0.5 text-gold"
                        : "rounded-sm border border-border px-2 py-0.5 text-muted"
                    }
                    title={role.id}
                  >
                    {role.name}
                    {role.allowed && " ✓"}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Card>

      <div className="flex items-center gap-3 lg:col-span-2">
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
