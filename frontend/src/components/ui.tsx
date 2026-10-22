/** Small UI primitives. One radius (6 px), 1 px rules, amber accent only for primary actions and focus. */
import { WarningCircle } from "@phosphor-icons/react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useId } from "react";
import { ApiError } from "../api/types";

export function Button({
  variant = "ghost",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" }) {
  const base =
    "press inline-flex h-8 items-center justify-center gap-2 rounded-[6px] px-3 text-[13px] whitespace-nowrap cursor-pointer disabled:cursor-not-allowed disabled:opacity-45";
  const look =
    variant === "primary"
      ? "bg-accent text-on-accent font-semibold hover:brightness-95"
      : "border border-line bg-surface text-fg-2 hover:text-fg hover:border-fg-3";
  return <button type="button" className={`${base} ${look} ${className}`} {...rest} />;
}

export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  columns = 4,
}: {
  label: string;
  options: { value: T; label: string; disabled?: boolean }[];
  value: T;
  onChange: (v: T) => void;
  columns?: number;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="grid overflow-hidden rounded-[6px] border border-line" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={o.disabled}
            onClick={() => onChange(o.value)}
            className={`press h-8 border-r border-b border-line text-[12px] last:border-r-0 disabled:opacity-40 ${on ? "bg-fg text-bg font-semibold" : "text-fg-2 hover:text-fg"}`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function Switch({ label, checked, onChange, disabled }: { label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className={`flex min-h-8 items-center justify-between gap-3 text-[13px] ${disabled ? "opacity-50" : "cursor-pointer"}`}>
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative h-[18px] w-[30px] shrink-0 rounded-full transition-colors duration-150 ${checked ? "bg-accent" : "bg-line"}`}
      >
        <span
          className="absolute top-[2px] left-[2px] h-[14px] w-[14px] rounded-full bg-white shadow-sm transition-transform duration-150"
          style={{ transform: checked ? "translateX(12px)" : "none", transitionTimingFunction: "var(--ease-out)" }}
        />
      </button>
    </label>
  );
}

export function Field({ label, help, error, children }: { label: string; help?: string; error?: string; children: (id: string, describedBy?: string) => ReactNode }) {
  const id = useId();
  const helpId = `${id}-help`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[12px] text-fg-2">
        {label}
      </label>
      {children(id, help || error ? helpId : undefined)}
      {error ? (
        <p id={helpId} role="alert" className="text-[11px] text-danger">
          {error}
        </p>
      ) : help ? (
        <p id={helpId} className="text-[11px] text-fg-3">
          {help}
        </p>
      ) : null}
    </div>
  );
}

export const inputClass =
  "h-8 w-full rounded-[6px] border border-line bg-surface px-2.5 text-[13px] text-fg outline-none focus-visible:border-accent";

export function Section({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between">
        <h2 className="text-[12px] font-semibold text-fg-2">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function SkeletonLines({ lines = 4 }: { lines?: number }) {
  return (
    <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton h-4" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function ErrorNote({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof ApiError ? `${error.message} (${error.code})` : error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="fade-in flex items-start gap-2 rounded-[6px] border border-danger/40 px-3 py-2 text-[12px] text-danger">
      <WarningCircle size={16} weight="bold" aria-hidden className="mt-px shrink-0" />
      <span className="flex-1">{msg}</span>
      {retry ? (
        <button type="button" className="underline" onClick={retry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-[12px] leading-relaxed text-fg-3">{children}</p>;
}

export function Stat({ k, v, s }: { k: string; v: string; s?: string }) {
  return (
    <div className="min-w-0 py-2.5 not-first:border-l not-first:border-line not-first:pl-3">
      <div className="text-[11px] text-fg-3">{k}</div>
      <div className="num mt-0.5 text-[20px] leading-tight font-medium">{v}</div>
      {s ? <div className="num text-[11px] text-fg-3">{s}</div> : null}
    </div>
  );
}
