import type { CSSProperties, ReactNode } from "react";

export function Glass({
  children,
  className = "",
  style,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div className={`glass ${className}`} style={style}>
      {children}
    </div>
  );
}

export function Pill({
  children,
  tone = "neutral",
  dot = false,
}: {
  children: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "error" | "info";
  dot?: boolean;
}) {
  return (
    <span className={`pill pill-${tone}`}>
      {dot && <span className="pill-dot" />}
      {children}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "glass",
  disabled,
  type = "button",
  full,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "glass" | "primary" | "danger" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  full?: boolean;
}) {
  return (
    <button
      type={type}
      className={`btn btn-${variant}${full ? " btn-full" : ""}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export function BatteryRing({
  value,
  label,
  charging,
}: {
  value: number | null;
  label?: string;
  charging?: boolean;
}) {
  const pct = value === null || value === undefined ? 0 : Math.max(0, Math.min(100, value));
  const r = 52;
  const circumference = 2 * Math.PI * r;
  const dash = (pct / 100) * circumference;
  const color =
    value === null ? "var(--muted)" : pct > 50 ? "var(--ok)" : pct > 20 ? "var(--warn)" : "var(--danger)";
  return (
    <div className="battery-ring">
      <svg viewBox="0 0 128 128" role="img" aria-label={`Batterie ${value ?? "?"} %`}>
        <defs>
          <linearGradient id="batteryGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.55" />
            <stop offset="100%" stopColor={color} />
          </linearGradient>
        </defs>
        <circle cx="64" cy="64" r={r} className="ring-track" />
        <circle
          cx="64"
          cy="64"
          r={r}
          className="ring-value"
          stroke="url(#batteryGrad)"
          strokeDasharray={`${dash} ${circumference}`}
        />
      </svg>
      <div className="battery-ring-label">
        <strong>{value === null || value === undefined ? "—" : `${value}%`}</strong>
        <span>{charging ? "en charge" : (label ?? "batterie")}</span>
      </div>
    </div>
  );
}

export function Sparkline({
  values,
  height = 56,
  color = "var(--accent)",
  area = true,
  min,
  max,
}: {
  values: number[];
  height?: number;
  color?: string;
  area?: boolean;
  min?: number;
  max?: number;
}) {
  if (!values.length) return null;
  const w = 100;
  const lo = min ?? Math.min(...values);
  const hi = max ?? Math.max(...values);
  const span = hi - lo || 1;
  const pts = values.map((v, i) => {
    const x = (i / Math.max(1, values.length - 1)) * w;
    const y = height - ((v - lo) / span) * (height - 6) - 3;
    return [x, y] as const;
  });
  const line = pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const poly = `0,${height} ${line} ${w},${height}`;
  return (
    <svg className="sparkline" viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.32" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {area && <polygon points={poly} fill="url(#sparkFill)" />}
      <polyline points={line} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

export function EmptyState({
  icon = "◌",
  title,
  children,
}: {
  icon?: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}

export function SectionTitle({
  title,
  aside,
}: {
  title: string;
  aside?: ReactNode;
}) {
  return (
    <div className="section-title">
      <h2>{title}</h2>
      {aside}
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="switch-row">
      <span>
        <span className="switch-label">{label}</span>
        {hint && <span className="switch-hint">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        className={`switch${checked ? " on" : ""}`}
        onClick={() => onChange(!checked)}
      >
        <span />
      </button>
    </label>
  );
}

export type Toast = { id: number; message: string; tone: "ok" | "error" | "info" };

export function Toasts({ items, onDismiss }: { items: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toasts">
      {items.map((t) => (
        <button key={t.id} className={`toast toast-${t.tone}`} onClick={() => onDismiss(t.id)}>
          {t.message}
        </button>
      ))}
    </div>
  );
}

export function Modal({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="glass modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Fermer">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
