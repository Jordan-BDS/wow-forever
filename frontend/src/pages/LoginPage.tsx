import { Navigate, useSearchParams } from "react-router";
import { discordLoginUrl, useMe } from "@/auth/useMe";
import { Emblem } from "@/components/Emblem";
import { Footer } from "@/components/Footer";
import { LOGIN_ERRORS } from "@/lib/roles";

export function LoginPage() {
  const me = useMe();
  const [params] = useSearchParams();
  const errorCode = params.get("error");

  if (me.data) return <Navigate to="/" replace />;

  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex flex-1 flex-col items-center justify-center px-4 py-12">
        <div className="banner w-full max-w-md rounded-md border border-gold-dark/50 px-8 pt-10 pb-8 text-center">
          <Emblem className="mx-auto size-24" />
          <h1 className="mt-5 font-display text-4xl text-gold">WoW Forever</h1>
          <div className="rule-gold mx-auto mt-3 w-40" />
          <p className="mt-3 text-sm text-muted">Par des zouaves, pour des zouaves.</p>
          {errorCode && (
            <p className="mt-6 rounded-sm border border-danger/50 bg-danger/10 p-3 text-sm text-danger">
              {LOGIN_ERRORS[errorCode] ?? "Connexion impossible."}
            </p>
          )}
          <a
            href={discordLoginUrl}
            className="mt-8 inline-flex w-full items-center justify-center gap-2 rounded-sm border border-gold-dark bg-gold px-4 py-3 font-medium text-bg transition-colors hover:border-gold-light hover:bg-gold-light hover:text-bg"
          >
            <DiscordLogo />
            Entrer avec Discord
          </a>
          <p className="mt-4 text-xs text-muted">
            Réservé aux membres du Discord de la guilde ayant le rôle « Membre ».
          </p>
        </div>
      </div>
      <Footer />
    </div>
  );
}

function DiscordLogo() {
  return (
    <svg viewBox="0 0 24 24" className="size-5 fill-current" aria-hidden="true">
      <path d="M20.317 4.37a19.8 19.8 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.3 18.3 0 0 0-5.487 0 12.6 12.6 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.7 19.7 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.1 13.1 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.009c.12.099.246.198.373.292a.077.077 0 0 1-.006.127 12.3 12.3 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.8 19.8 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03M8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418m7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418" />
    </svg>
  );
}
