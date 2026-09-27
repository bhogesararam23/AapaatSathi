import {
  BarChart2,
  CheckCircle2,
  ChevronRight,
  Droplets,
  Gauge,
  MapPin,
  Phone,
  Siren,
  TrendingUp,
  Users,
} from "lucide-react";
import { useMemo } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import type { Alert, Factor, HazardReport, Level, WardRiskSummary } from "../api/types";
import { useSession } from "../state/session";
import {
  Bar as MiniBar,
  ConfidenceMeter,
  LEVEL_COLOR,
  LevelBadge,
  compactNumber,
  formatNumber,
  timeAgo,
  useToast,
} from "./ui";

/* ------------------------------------------------------------------ alerts */

export function AlertBanner({ alerts }: { alerts: Alert[] }) {
  const { t, i18n } = useTranslation();
  const toast = useToast();
  const { user } = useSession();
  const top = alerts[0];
  if (!top) return null;

  const lang = (i18n.language === "hi" || i18n.language === "gar" ? i18n.language : "en") as "en" | "hi" | "gar";
  const localised = top.localized?.[lang]?.sms || top.message;
  const color = LEVEL_COLOR[top.level];

  return (
    <div
      className="rounded-2xl overflow-hidden border mb-5 animate-slide"
      style={{ borderColor: color, background: `${color}0f` }}
      role="alert"
    >
      <div className="flex items-stretch">
        <div className="w-1.5 shrink-0" style={{ background: color }} />
        <div className="flex-1 min-w-0 px-4 py-3.5 flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="w-8 h-8 rounded-full grid place-items-center shrink-0" style={{ background: color }}>
            <Siren size={16} className="text-white" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-bold uppercase tracking-widest" style={{ color }}>
              {top.auto_issued ? "Automatic warning" : "District control room"} · {top.code}
            </p>
            <p
              className={`text-[15px] font-bold text-ink-950 leading-snug ${lang !== "en" ? "deva" : ""}`}
            >
              {top.ward_name ? `${top.ward_name}: ` : ""}
              {localised}
            </p>
            <p className="text-[11px] text-ink-600 mt-1">
              {t("level." + top.level)} · {timeAgo(top.issued_at)} ·{" "}
              {top.expires_at ? `expires in ${Math.max(0, Math.round((new Date(top.expires_at).getTime() - Date.now()) / 60000))} min` : "no expiry"}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {top.minutes_left !== null && top.minutes_left !== undefined && (
              <span className="pill tabular">{top.minutes_left} min left</span>
            )}
            <button
              className="btn btn-sm"
              style={{ background: color, color: "#fff" }}
              onClick={async () => {
                try {
                  await api.ackAlert(top.code);
                  toast(`Acknowledged ${top.code}. The control room can see your ack.`, "success");
                } catch (e) {
                  toast((e as Error).message, "error");
                }
              }}
            >
              <CheckCircle2 size={14} /> I have seen this{user ? "" : ""}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------- the explainability panel */

export function FactorBreakdown({
  factors,
  level,
  compact = false,
}: {
  factors: Factor[];
  level: Level;
  compact?: boolean;
}) {
  const sorted = useMemo(() => [...factors].sort((a, b) => b.contribution - a.contribution), [factors]);
  const total = sorted.reduce((s, f) => s + f.contribution, 0);
  const max = Math.max(...sorted.map((f) => f.contribution), 1);

  return (
    <div>
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <p className="eyebrow">Why this score</p>
          <p className="text-[11px] text-ink-400 mt-0.5">
            Weighted sum of ten factors, {sorted.length} shown. Base total {total.toFixed(1)} before crowd
            corroboration.
          </p>
        </div>
        <span className="text-2xl font-extrabold tabular" style={{ color: LEVEL_COLOR[level] }}>
          {Math.round(total)}
        </span>
      </div>

      <div className="grid gap-2">
        {sorted.map((f) => (
          <FactorRow key={f.key} factor={f} share={f.contribution / max} compact={compact} />
        ))}
      </div>
    </div>
  );
}

function FactorRow({ factor, share, compact }: { factor: Factor; share: number; compact: boolean }) {
  const tone = factor.contribution / (factor.weight * 100) > 0.66 ? "#dc2626" : factor.contribution / (factor.weight * 100) > 0.33 ? "#f97316" : "#0ea5e9";
  return (
    <details className="group rounded-lg border border-[var(--line)] bg-white open:bg-ink-100/40 transition-colors">
      <summary className="cursor-pointer list-none px-3 py-2 flex items-center gap-3">
        <span className="w-1.5 h-8 rounded-full shrink-0" style={{ background: tone }} />
        <span className="flex-1 min-w-0">
          <span className="block text-[13px] font-semibold text-ink-900 truncate">{factor.label}</span>
          {!compact && (
            <span className="block text-[11px] text-ink-400">
              observed {factor.observed}
              {factor.unit !== "index" ? ` ${factor.unit}` : ""} · weight {(factor.weight * 100).toFixed(0)}%
            </span>
          )}
        </span>
        <span className="w-20 shrink-0 hidden sm:block">
          <MiniBar value={share} max={1} color={tone} height={5} />
        </span>
        <span className="text-[13px] font-bold tabular w-12 text-right shrink-0" style={{ color: tone }}>
          +{factor.contribution.toFixed(1)}
        </span>
        <ChevronRight size={14} className="text-ink-400 shrink-0 transition-transform group-open:rotate-90" />
      </summary>
      <div className="px-3 pb-3 pl-6 text-[12px] text-ink-600 leading-relaxed border-t border-[var(--line)] pt-2.5">
        <p>{factor.rationale}</p>
        <p className="text-[11px] text-ink-400 mt-1.5 font-mono">
          normalised {factor.normalised.toFixed(3)} × weight {factor.weight.toFixed(2)} × 100 = {factor.contribution.toFixed(2)}
        </p>
      </div>
    </details>
  );
}

/* --------------------------------------------------------------- rain chart */

export function RainChart({
  series,
  height = 150,
}: {
  series: { at: string; rain_mm: number; forecast: boolean }[];
  height?: number;
}) {
  const data = useMemo(
    () =>
      series.map((p) => ({
        hour: new Date(p.at).toLocaleString("en-IN", { hour: "2-digit", day: "2-digit", month: "short" }),
        rain: p.rain_mm,
        forecast: p.forecast,
      })),
    [series],
  );

  if (!data.length) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="eyebrow flex items-center gap-1.5">
          <Droplets size={12} /> Rainfall · last 48 h + forecast
        </p>
        <div className="flex items-center gap-2.5 text-[10px] text-ink-400 font-semibold">
          <span className="flex items-center gap-1">
            <i className="w-2 h-2 rounded-sm bg-risk-blue inline-block" />
            observed
          </span>
          <span className="flex items-center gap-1">
            <i className="w-2 h-2 rounded-sm bg-risk-orange inline-block" />
            forecast
          </span>
        </div>
      </div>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
            <XAxis dataKey="hour" tick={{ fontSize: 9, fill: "#8ea0bd" }} interval={5} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 9, fill: "#8ea0bd" }} tickLine={false} axisLine={false} unit="" width={44} />
            <Tooltip
              formatter={(v: number) => [`${v} mm`, "rain"]}
              contentStyle={{ fontSize: 11, borderRadius: 10, border: "1px solid #dde5f0" }}
              labelStyle={{ fontWeight: 600 }}
            />
            <ReferenceLine x={data[Math.floor(data.length / 2)]?.hour} stroke="#c3d0e4" strokeDasharray="3 3" />
            <Bar dataKey="rain" radius={[2, 2, 0, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.forecast ? "#f97316" : "#0ea5e9"} fillOpacity={d.forecast ? 0.55 : 0.9} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- ward header */

export function WardSummary({ ward }: { ward: WardRiskSummary }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
      <div
        className="relative w-24 h-24 rounded-full grid place-items-center shrink-0"
        style={{
          background: `conic-gradient(${LEVEL_COLOR[ward.level]} ${ward.score * 3.6}deg, #e6ecf5 0deg)`,
        }}
      >
        <div className="absolute inset-2 bg-white rounded-full grid place-items-center text-center">
          <div>
            <p className="text-2xl font-extrabold tabular leading-none" style={{ color: LEVEL_COLOR[ward.level] }}>
              {Math.round(ward.score)}
            </p>
            <p className="text-[9px] font-bold uppercase tracking-wider text-ink-400 mt-0.5">/ 100</p>
          </div>
        </div>
      </div>

      <div className="min-w-0">
        <LevelBadge level={ward.level} size="lg" label={t(`level.${ward.level}`)} />
        <p className="text-[13px] text-ink-600 mt-2 leading-relaxed max-w-md">{t(`advice.${ward.level}`)}</p>
        <p className="text-[11px] text-ink-400 mt-1.5 font-mono">
          {ward.code} · model {ward.model_version}
        </p>
      </div>

      <div className="flex flex-wrap gap-x-7 gap-y-3 ml-auto">
        <Stat
          Icon={TrendingUp}
          label="Chance in 24 h"
          value={`${Math.round(ward.probability_24h * 100)}%`}
          tone={LEVEL_COLOR[ward.level]}
        />
        <Stat Icon={Users} label="People exposed" value={compactNumber(ward.population_at_risk)} />
        <Stat Icon={Gauge} label="Crowd uplift" value={`×${ward.crowd_uplift.toFixed(2)}`} />
        <Stat
          Icon={MapPin}
          label="Ground reports"
          value={`${ward.inputs.open_reports + ward.inputs.confirmed_reports}`}
          hint={`${ward.inputs.confirmed_reports} confirmed`}
        />
      </div>
    </div>
  );
}

function Stat({
  Icon,
  label,
  value,
  hint,
  tone,
}: {
  Icon: typeof Users;
  label: string;
  value: string;
  hint?: string;
  tone?: string;
}) {
  return (
    <div>
      <p className="eyebrow flex items-center gap-1">
        <Icon size={11} />
        {label}
      </p>
      <p className="text-xl font-extrabold tabular mt-1" style={tone ? { color: tone } : undefined}>
        {value}
      </p>
      {hint && <p className="text-[10px] text-ink-400">{hint}</p>}
    </div>
  );
}

/* --------------------------------------------------------------- report row */

export function ReportRow({ report, onOpen }: { report: HazardReport; onOpen?: (code: string) => void }) {
  const tone =
    report.status === "confirmed"
      ? "#dc2626"
      : report.status === "under_review"
        ? "#f97316"
        : report.status === "new"
          ? "#0ea5e9"
          : "#94a3b8";
  return (
    <div className="table-row grid-cols-[1fr_auto] sm:grid-cols-[1fr_auto_auto]">
      <div className="min-w-0">
        <p className="text-[13px] font-semibold text-ink-900 truncate">{report.title || report.hazard_type}</p>
        <p className="text-[11px] text-ink-400 truncate">
          {report.hazard_type.replace("_", " ")}
          {report.ward_name ? ` · ${report.ward_name}` : ""} · {timeAgo(report.created_at)} ·{" "}
          {report.corroborated_by} corroboration{report.corroborated_by === 1 ? "" : "s"}
          {report.source === "sms" ? " · via SMS" : ""}
        </p>
      </div>
      <span className="chip" style={{ background: `${tone}1a`, color: tone }}>
        {report.status.replace("_", " ")}
      </span>
      <div className="hidden sm:flex items-center gap-2">
        <span className="text-[11px] font-bold tabular text-ink-600 w-10 text-right">
          {Math.round(report.confidence * 100)}%
        </span>
        {onOpen && (
          <button className="btn-ghost btn-sm" onClick={() => onOpen(report.code)}>
            Open
          </button>
        )}
      </div>
    </div>
  );
}

export function ConfidenceStrip({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1">
        <ConfidenceMeter value={value} />
      </div>
    </div>
  );
}

export function ShelterContact({ phone, name }: { phone: string; name: string }) {
  if (!phone) return null;
  return (
    <a
      href={`tel:${phone.replace(/[^\d+]/g, "")}`}
      className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-risk-blue hover:underline"
    >
      <Phone size={12} /> {name || "Call"}
    </a>
  );
}

export function ChartFallback({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-ink-400">
      <BarChart2 size={12} /> {label}
    </div>
  );
}

export function formatPopulation(n: number): string {
  return formatNumber(n);
}
