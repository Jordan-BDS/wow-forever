import clsx from "clsx";
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, SelectHTMLAttributes } from "react";
import type { SiteRole } from "@/api/client";
import { ROLE_LABELS } from "@/lib/roles";

type Variant = "primary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-gold text-bg hover:bg-gold-dark",
  ghost: "border border-border bg-transparent text-text hover:bg-surface-2",
  danger: "border border-danger/60 text-danger hover:bg-danger/10",
};

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={clsx("rounded-lg border border-border bg-surface p-4 shadow-lg", className)} {...props} />
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={clsx(
        "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-text",
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
        "rounded-md border border-border bg-bg px-2 py-1.5 text-sm text-text focus:border-gold focus:outline-none",
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
  gm: "bg-gold/20 text-gold border-gold/40",
  officer: "bg-alliance/20 text-alliance border-alliance/40",
  member: "bg-surface-2 text-muted border-border",
};

export function RoleBadge({ role }: { role: SiteRole }) {
  return (
    <span className={clsx("rounded border px-1.5 py-0.5 text-xs font-medium", roleStyles[role])}>
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

export function PageTitle({ children, actions }: { children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <h1 className="font-display text-2xl text-gold">{children}</h1>
      {actions}
    </div>
  );
}
