import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-white shadow-glow hover:bg-accent-strong",
  secondary: "border border-line bg-white/[0.04] text-slate-100 hover:bg-white/[0.08]",
  ghost: "text-slate-300 hover:bg-white/[0.06] hover:text-white",
  danger: "border border-red-500/30 bg-red-500/10 text-red-200 hover:bg-red-500/20",
};

export function Button({ className = "", variant = "primary", size = "md", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  const sizing = size === "sm" ? "h-8 px-2.5 text-xs" : "h-9 px-3.5 text-sm";
  return <button className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 disabled:cursor-not-allowed disabled:opacity-40 ${sizing} ${variants[variant]} ${className}`} {...props} />;
}

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`h-9 w-full rounded-lg border border-line bg-black/30 px-3 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-accent/60 focus:ring-2 focus:ring-accent/20 ${className}`} {...props} />;
}

export function Textarea({ className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`w-full resize-none rounded-lg border border-line bg-black/30 px-3 py-2 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-accent/60 focus:ring-2 focus:ring-accent/20 ${className}`} {...props} />;
}

export function Card({ className = "", children, title, action }: { className?: string; children: ReactNode; title?: ReactNode; action?: ReactNode }) {
  return (
    <section className={`rounded-2xl border border-line bg-panel/80 shadow-panel backdrop-blur ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold tracking-tight text-slate-100">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

const tones = {
  neutral: "bg-white/[0.06] text-slate-300 ring-white/10",
  info: "bg-sky-500/10 text-sky-200 ring-sky-400/20",
  success: "bg-emerald-500/10 text-emerald-200 ring-emerald-400/20",
  warning: "bg-amber-500/10 text-amber-200 ring-amber-400/20",
  error: "bg-red-500/10 text-red-200 ring-red-400/20",
  accent: "bg-accent/15 text-blue-100 ring-accent/30",
} as const;

export type Tone = keyof typeof tones;

export function Badge({ tone = "neutral", children, className = "" }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${tones[tone]} ${className}`}>{children}</span>;
}

export function Spinner({ className = "" }: { className?: string }) {
  return <span aria-hidden className={`inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent ${className}`} />;
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-accent/10 text-accent-soft">{icon}</div>
      <p className="text-sm font-medium text-slate-200">{title}</p>
      {children && <p className="mt-1 max-w-xs text-xs leading-relaxed text-slate-500">{children}</p>}
    </div>
  );
}

const statusTone: Record<string, Tone> = {
  queued: "neutral", uploaded: "neutral", running: "info", ready: "success", succeeded: "success",
  failed: "error", cancelled: "warning", waiting_for_approval: "warning", revision_requested: "warning",
};

export function StatusBadge({ status }: { status: string }) {
  const busy = status === "running" || status === "queued" || status === "uploaded";
  return <Badge tone={statusTone[status] ?? "neutral"}>{busy && <Spinner className="h-2.5 w-2.5 border" />}{status.replace(/_/g, " ")}</Badge>;
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

export function formatDuration(ms?: number | null) {
  if (!ms) return "";
  const seconds = Math.round(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
