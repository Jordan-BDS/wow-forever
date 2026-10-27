import { Navigate, Outlet } from "react-router";
import { Spinner } from "@/components/ui";
import { useMe } from "./useMe";

export function RequireAuth() {
  const me = useMe();
  if (me.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }
  if (me.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center text-danger">
        Impossible de joindre le serveur. Réessaie dans un instant.
      </div>
    );
  }
  if (!me.data) return <Navigate to="/login" replace />;
  return <Outlet context={me.data} />;
}
