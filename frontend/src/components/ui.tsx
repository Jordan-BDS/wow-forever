import clsx from "clsx";
import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import type { SiteRole } from "@/api/client";
import { ROLE_LABELS } from "@/lib/roles";

type Variant = "primary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "border border-gold-dark bg-gold text-bg hover:bg-gold-light hover:border-gold-light",
  ghost: "border border-border bg-transparent text-text hover:border-gold hover:text-gold",
  danger: "border border-danger/50 text-danger hover:border-danger hover:bg-danger/10",
};

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-sm px-3.5 py-2 text-sm font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

/** Carte : tissu de bannière légèrement translucide (le fond affleure), bordure fine, liseré plus clair en haut. */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx(
        "min-w-0 rounded-md border border-border bg-surface/90 bg-gradient-to-b from-surface-2/40 to-surface/90 p-4",
        className,
      )}
      {...props}
    />
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={clsx(
        "w-full rounded-sm border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-muted/70",
        "focus:border-gold focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={clsx(
        "w-full rounded-sm border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-muted/70",
        "focus:border-gold focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={clsx(
        "rounded-sm border border-border bg-bg px-2 py-1.5 text-sm text-text focus:border-gold focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="text-muted">{label}</span>
      {children}
    </label>
  );
}

const roleStyles: Record<SiteRole, string> = {
  gm: "border-gold/60 text-gold",
  officer: "border-royal text-[#8fb0ea]",
  member: "border-border text-muted",
};

export function RoleBadge({ role }: { role: SiteRole }) {
  return (
    <span className={clsx("rounded-sm border px-1.5 py-0.5 text-xs", roleStyles[role])}>
      {ROLE_LABELS[role]}
    </span>
  );
}

export function Spinner() {
  return (
    <div
      role="status"
      aria-label="Chargement"
      className="size-6 animate-spin rounded-full border-2 border-border border-t-gold"
    />
  );
}

/** Titre de page en capitales romaines gravées, souligné d'un court filet d'or. */
export function PageTitle({ children, actions }: { children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <h1 className="font-display text-3xl text-text after:mt-2 after:block after:h-px after:w-14 after:bg-gold">
        {children}
      </h1>
      {actions}
    </div>
  );
}
