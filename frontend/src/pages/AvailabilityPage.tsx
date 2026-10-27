import { Link } from "react-router";
import { useGuildAvailability, useMembers } from "@/api/hooks";
import { AvailabilityGrid } from "@/components/AvailabilityGrid";
import { Button, Card, PageTitle, Spinner } from "@/components/ui";
import { namesByCell } from "@/lib/availability";

export function AvailabilityPage() {
  const availability = useGuildAvailability();
  const members = useMembers();
  if (availability.isPending || members.isPending) return <Spinner />;

  const slots = availability.data ?? [];
  const contributors = new Set(slots.map((s) => s.user)).size;
  const activeMembers = (members.data ?? []).filter((m) => m.is_active).length;

  return (
    <>
      <PageTitle
        actions={
          <Link to="/profil">
            <Button variant="ghost">Renseigner les miennes</Button>
          </Link>
        }
      >
        Disponibilités de la guilde
      </PageTitle>
      <Card>
        <p className="mb-3 text-sm text-muted">
          {contributors} membre{contributors > 1 && "s"} sur {activeMembers} ont renseigné leurs créneaux.
          Plus la case est verte, plus il y a de monde ; survole pour voir qui.
        </p>
        <AvailabilityGrid mode="heatmap" names={namesByCell(slots)} total={Math.max(contributors, 1)} />
      </Card>
    </>
  );
}
