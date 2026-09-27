import { AlertTriangle, Check, Info, Loader2, RefreshCw, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Level } from "../api/types";
import { LEVEL_ORDER } from "../api/types";

/* ------------------------------------------------------------------ colours */

export const LEVEL_COLOR: Record<Level, string> = {
  green: "#16a34a",
  blue: "#0ea5e9",
  yellow: "#ca8a04",
  orange: "#f97316",
  red: "#dc2626",
};

export const LEVEL_BG: Record<Level, string> = {
  green: "#f0fdf4",
  blue: "#f0f9ff",
  yellow: "#fefce8",
  orange: "#fff7ed",
  red: "#fef2f2",
};

export const LEVEL_LABEL_EN: Record<Level, string> = {
  green: "Safe",
  blue: "Advisory",
  yellow: "Alert",
  orange: "Warning",
  red: "Evacuate",
};

/** 0-100 score → the level the backend would assign (kept in sync client-side for paint). */
export function levelOf(score: number): Level {
  if (score >= 76) return "red";
  if (score >= 62) return "orange";
  if (score >= 45) return "yellow";
  if (score >= 25) return "blue";
  return "green";
}

export function isHigh(level: Level) {
  return level === "orange" || level === "red";
}

export function rank(level: Level) {
  return LEVEL_ORDER.indexOf(level);
}

/* -------------------------------------------------------------------- atoms */

export function LevelBadge({
  level,
  label,
  size = "md",
  showDot = true,
}: {
  level: Level;
  label?: string;
  size?: "sm" | "md" | "lg";
  showDot?: boolean;
}) {
  const px =
    size === "lg"
      ? "text-sm px-3.5 py-1.5"
      : size === "sm"
        ? "text-[10px] px-2 py-0.5"
        : "text-[11px] px-2.5 py-1";
  return (
    <span
      className={`chip ${px} uppercase`}
      style={{ background: LEVEL_COLOR[level], color: "#fff", letterSpacing: "0.06em" }}
    >
      {showDot && (
        <span
          className="w-1.5 h-1.5 rounded-full bg-white/90 inline-block"
          style={{ animation: isHigh(level) ? "pulseRing 1.8s ease-out infinite" : undefined }}
        />
      )}
      {label ?? LEVEL_LABEL_EN[level]}
    </span>
  );
}

export function Card({
  title,
  subtitle,
  actions,
  children,
  className = "",
  bodyClass = "p-4 sm:p-5",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
}) {
  return (
    <section className={`panel overflow-hidden ${className}`}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 px-4 sm:px-5 py-3.5 border-b border-[var(--line)]">
          <div className="min-w-0">
            {title && <h3 className="text-[15px] font-bold leading-tight">{title}</h3>}
            {subtitle && <p className="text-xs text-ink-400 mt-0.5 leading-snug">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "default",
  size = "md",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | Level | "muted";
  size?: "sm" | "md" | "lg";
}) {
  const color = tone !== "default" && tone !== "muted" ? LEVEL_COLOR[tone] : undefined;
  return (
    <div className="min-w-0">
      <p className="eyebrow truncate">{label}</p>
      <p
        className={[
          "font-extrabold tabular leading-none mt-1.5",
          size === "lg" ? "text-3xl sm:text-4xl" : size === "sm" ? "text-lg" : "text-2xl",
          tone === "muted" ? "text-ink-400" : "text-ink-950",
        ].join(" ")}
        style={color ? { color } : undefined}
      >
        {value}
      </p>
      {hint && <p className="text-[11px] text-ink-400 mt-1.5 leading-snug">{hint}</p>}
    </div>
  );
}

/** Horizontal contribution bar — the visual backbone of the explainability panel. */
export function Bar({
  value,
  max = 1,
  color = "#0ea5e9",
  height = 6,
  track = "#e6ecf5",
}: {
  value: number;
  max?: number;
  color?: string;
  height?: number;
  track?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / (max || 1)) * 100));
  return (
    <div className="w-full rounded-full overflow-hidden" style={{ height, background: track }}>
      <div
        className="h-full rounded-full transition-[width] duration-500 ease-out"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

/** Tiny inline trend line, drawn as SVG so we do not ship a chart lib for it. */
export function Spark({
  points,
  width = 120,
  height = 30,
  color = "#0ea5e9",
  fill = true,
}: {
  points: number[];
  width?: number;
  height?: number;
  color?: string;
  fill?: boolean;
}) {
  if (points.length < 2) return <div className="text-[10px] text-ink-400">no series</div>;
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const coords = points.map((p, i) => [i * step, height - ((p - min) / span) * (height - 4) - 2]);
  const d = coords.map((c, i) => `${i ? "L" : "M"}${c[0].toFixed(1)} ${c[1].toFixed(1)}`).join(" ");
  const area = `${d} L${width} ${height} L0 ${height} Z`;
  return (
    <svg width={width} height={height} className="overflow-visible" role="img" aria-label="trend">
      {fill && <path d={area} fill={color} opacity={0.1} />}
      <path d={d} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function ConfidenceMeter({ value }: { value: number }) {
  // Confidence is about honesty, so it is labelled in words as well as a bar.
  const word = value >= 0.75 ? "well measured" : value >= 0.55 ? "mostly modelled" : "terrain prior only";
  const color = value >= 0.75 ? "#16a34a" : value >= 0.55 ? "#ca8a04" : "#64748b";
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="eyebrow">Data confidence</span>
        <span className="text-xs font-bold tabular" style={{ color }}>
          {Math.round(value * 100)}% · {word}
        </span>
      </div>
      <Bar value={value} color={color} height={5} />
    </div>
  );
}

/* ------------------------------------------------------------------ states */

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink-400">
      <Loader2 size={16} className="animate-spin" />
      {label}
    </span>
  );
}

export function Loading({ label = "Loading ward risk…" }: { label?: string }) {
  return (
    <div className="grid gap-3" role="status" aria-live="polite">
      <div className="skeleton h-28" />
      <div className="skeleton h-44" />
      <p className="text-xs text-ink-400">{label}</p>
    </div>
  );
}

export function SkeletonRows({ rows = 5, height = 56 }: { rows?: number; height?: number }) {
  return (
    <div className="grid gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height }} />
      ))}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  compact = false,
}: {
  error: Error | string;
  onRetry?: () => void;
  compact?: boolean;
}) {
  const message = typeof error === "string" ? error : error.message;
  const offline = /failed to fetch|network|cannot reach/i.test(message);
  return (
    <div
      className={`flex items-start gap-3 rounded-xl border px-4 py-3 ${
        compact ? "text-sm" : ""
      }`}
      style={{
        background: offline ? "#fff7ed" : "#fef2f2",
        borderColor: offline ? "#fed7aa" : "#fecaca",
      }}
      role="alert"
    >
      <AlertTriangle size={18} className="shrink-0 mt-0.5" color={offline ? "#f97316" : "#dc2626"} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-ink-900">
          {offline ? "API not reachable" : "Could not load this"}
        </p>
        <p className="text-xs text-ink-600 mt-0.5 break-words leading-relaxed">{message}</p>
        {offline && (
          <p className="text-[11px] text-ink-400 mt-1.5">
            Start it with <code className="font-mono bg-white/70 px-1 rounded">uvicorn app.main:app --reload</code> in
            the <code className="font-mono">backend</code> folder.
          </p>
        )}
      </div>
      {onRetry && (
        <button className="btn-ghost btn-sm shrink-0" onClick={onRetry}>
          <RefreshCw size={13} /> Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="text-center py-10 px-4">
      <div className="mx-auto w-10 h-10 rounded-full bg-ink-100 grid place-items-center mb-3 text-ink-400">
        {icon ?? <Info size={18} />}
      </div>
      <p className="text-sm font-semibold text-ink-700">{title}</p>
      {hint && <p className="text-xs text-ink-400 mt-1 max-w-xs mx-auto leading-relaxed">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------- toasts */

interface Toast {
  id: number;
  message: string;
  tone: "success" | "error" | "info" | Level;
}

const ToastCtx = createContext<(message: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);

  const push = useCallback((message: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev, { id, message, tone }]);
    window.setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 5200);
  }, []);

  const value = useMemo(() => push, [push]);

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[70] flex flex-col gap-2 w-[min(92vw,26rem)] pointer-events-none">
        {items.map((t) => (
          <ToastRow key={t.id} toast={t} onDismiss={() => setItems((p) => p.filter((x) => x.id !== t.id))} />
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

function ToastRow({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const tone = toast.tone;
  const bg =
    tone === "success" ? "#065f46" : tone === "error" ? "#7f1d1d" : tone in LEVEL_COLOR ? LEVEL_COLOR[tone as Level] : "#0b1220";
  return (
    <div
      className="animate-slide pointer-events-auto flex items-start gap-2.5 rounded-xl px-4 py-3 text-white text-sm shadow-2xl"
      style={{ background: bg }}
      role="status"
    >
      {tone === "success" ? <Check size={16} className="mt-0.5 shrink-0" /> : <Info size={16} className="mt-0.5 shrink-0" />}
      <p className="flex-1 leading-snug">{toast.message}</p>
      <button onClick={onDismiss} className="opacity-70 hover:opacity-100 shrink-0" aria-label="Dismiss">
        <X size={15} />
      </button>
    </div>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}

/* -------------------------------------------------------------------- misc */

export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const mins = Math.max(0, Math.round((now - then) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} h ${mins % 60 ? `${mins % 60} m ` : ""}ago`;
  const days = Math.floor(hrs / 24);
  return `${days} day${days > 1 ? "s" : ""} ago`;
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-IN");
}

/** Indian short scale: 1,10,000 reads as "1.1 lakh", not "110K". */
export function compactNumber(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (n >= 10_000_000) return `${(n / 10_000_000).toFixed(1)} Cr`;
  if (n >= 100_000) return `${(n / 100_000).toFixed(1)} lakh`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(Math.round(n));
}
