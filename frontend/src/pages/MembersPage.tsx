import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { api, errorMessage, type Member, type SiteRole } from "@/api/client";
import { useCurrentUser } from "@/auth/useCurrentUser";
import { Button, Card, PageTitle, RoleBadge, Select, Spinner } from "@/components/ui";
import { isOfficerOrAbove, outranks, ROLE_LABELS, ROLES } from "@/lib/roles";

const MEMBERS_KEY = ["members"] as const;

function useMembers() {
  return useQuery({
    queryKey: MEMBERS_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/members/");
      if (error || !data) throw new Error("Liste des membres indisponible");
      return data;
    },
  });
}

export function MembersPage() {
  const me = useCurrentUser();
  const members = useMembers();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: MEMBERS_KEY });

  const setActive = useMutation({
    mutationFn: async ({ member, active }: { member: Member; active: boolean }) => {
      const path = active ? "/api/members/{id}/reactivate/" : "/api/members/{id}/deactivate/";
      const { error } = await api.POST(path, { params: { path: { id: member.id } } });
      if (error) throw error;
    },
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const setRole = useMutation({
    mutationFn: async ({ member, role }: { member: Member; role: SiteRole }) => {
      const { error } = await api.POST("/api/members/{id}/role/", {
        params: { path: { id: member.id } },
        body: { site_role: role },
      });
      if (error) throw error;
    },
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const canManage = isOfficerOrAbove(me.site_role);
  const busy = setActive.isPending || setRole.isPending;

  return (
    <>
      <PageTitle>Membres</PageTitle>
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}
      <Card className="overflow-x-auto p-0">
        {members.isPending ? (
          <div className="flex justify-center p-8">
            <Spinner />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs text-muted">
              <tr>
                <th className="px-3 py-3 sm:px-4">Membre</th>
                <th className="hidden px-3 py-3 sm:table-cell sm:px-4">Discord</th>
                <th className="px-3 py-3 sm:px-4">Rôle</th>
                <th className="px-3 py-3 sm:px-4">Statut</th>
                {canManage && <th className="px-3 py-3 text-right sm:px-4">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {members.data?.map((member) => {
                const isMe = member.id === me.id;
                const manageable = canManage && !isMe && outranks(me.site_role, member.site_role);
                return (
                  <tr
                    key={member.id}
                    className={clsx("border-b border-border/60", !member.is_active && "opacity-60")}
                  >
                    <td className="px-3 py-2 sm:px-4">
                      <div className="flex items-center gap-3">
                        <img src={member.avatar_url} alt="" className="size-8 shrink-0 rounded-full" />
                        <span className="font-medium">{member.display_name}</span>
                        {isMe && <span className="text-xs text-muted">(toi)</span>}
                      </div>
                    </td>
                    <td className="hidden px-3 py-2 text-muted sm:table-cell sm:px-4">
                      {member.discord_username}
                    </td>
                    <td className="px-3 py-2 sm:px-4">
                      {me.site_role === "gm" && !isMe ? (
                        <Select
                          value={member.site_role}
                          disabled={busy}
                          aria-label={`Rôle de ${member.display_name}`}
                          onChange={(e) => setRole.mutate({ member, role: e.target.value as SiteRole })}
                        >
                          {ROLES.map((role) => (
                            <option key={role} value={role}>
                              {ROLE_LABELS[role]}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <RoleBadge role={member.site_role} />
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 sm:px-4">
                      {member.is_active ? (
                        <span className="text-success">Actif</span>
                      ) : (
                        <span className="text-danger">
                          Désactivé
                          {member.deactivation_reason === "discord" && " (Discord)"}
                        </span>
                      )}
                    </td>
                    {canManage && (
                      <td className="whitespace-nowrap px-3 py-2 text-right sm:px-4">
                        {manageable && (
                          <Button
                            variant={member.is_active ? "danger" : "ghost"}
                            disabled={busy}
                            onClick={() => setActive.mutate({ member, active: !member.is_active })}
                          >
                            {member.is_active ? "Désactiver" : "Réactiver"}
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
