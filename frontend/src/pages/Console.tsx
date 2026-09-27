import {
  Activity,
  Bell,
  FlaskConical,
  Gauge,
  Play,
  RefreshCw,
  ScrollText,
  Send,
  ShieldAlert,
  Truck,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../api/client";
import type { CoverageRow, HazardReport, Level, WardRiskSummary } from "../api/types";
import { LEVEL_COLOR, LevelBadge, compactNumber, formatNumber, timeAgo, useToast } from "../components/ui";
import { FactorBreakdown } from "../components/briefing";
import { RiskMap } from "../components/RiskMap";
import { useAsync, useNow } from "../hooks";
import { useLive } from "../state/live";
import { useSession } from "../state/session";

type Tab = "board" | "warnings" | "drill" | "delivery" | "audit";

const TABS: { key: Tab; label: string; Icon: typeof Gauge }[] = [
  { key: "board", label: "Risk board", Icon: Activity },
  { key: "warnings", label: "Issue warning", Icon: ShieldAlert },
  { key: "drill", label: "Scenario / drill", Icon: FlaskConical },
  { key: "delivery", label: "Delivery proof", Icon: Truck },
  { key: "audit", label: "Audit trail", Icon: ScrollText },
];

export default function Console() {
  const [tab, setTab] = useState<Tab>("board");
  const { status, updates } = useLive();
  const { user } = useSession();

  return (
    <div className="ops -mx-4 sm:-mx-6 -mt-5 sm:-mt-7 px-4 sm:px-6 py-5 min-h-[calc(100vh-3.5rem)]">
      <div className="max-w-[1400px] mx-auto">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-5">
          <div>
            <p className="ops-label flex items-center gap-2">
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: status === "open" ? "#22c55e" : "#eab308" }}
              />
              district operations console
            </p>
            <h1 className="text-white text-2xl sm:text-[26px] mt-1 leading-tight">
              {user?.district_id ? "Control room" : "All-district"} watch view
            </h1>
            <p className="text-ink-300 text-[13px] mt-1 max-w-2xl leading-relaxed">
              Live susceptibility across every mapped ward, the warnings already out, and the proof of who was
              actually reached. {updates} updates streamed this session.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="ops-panel px-3 py-2 text-[11px] font-mono text-ink-300">
              ws {status}
            </span>
          </div>
        </div>

        <div className="flex gap-1.5 mb-5 overflow-x-auto no-scrollbar">
          {TABS.map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-[13px] font-semibold whitespace-nowrap transition-all ${
                tab === key
                  ? "bg-white text-ink-950 shadow-lg"
                  : "ops-panel text-ink-300 hover:text-white hover:bg-white/10"
              }`}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>

        {tab === "board" && <RiskBoard />}
        {tab === "warnings" && <WarningsTab />}
        {tab === "drill" && <DrillTab />}
        {tab === "delivery" && <DeliveryTab />}
        {tab === "audit" && <AuditTab />}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- board */

function RiskBoard() {
  const { revision } = useLive();
  const now = useNow();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const overview = useAsync(() => api.overview(), [revision]);
  const analytics = useAsync(() => api.analytics(), [revision]);
  const series = useAsync(() => api.timeseries(24), [revision]);
  const coverage = useAsync(() => api.coverage(), [revision]);
  const reports = useAsync(() => api.reports({ needs_review: true, limit: 8 }), [revision]);

  const wards = overview.data?.wards ?? [];
  const chosen = wards.find((w) => w.code === selected) ?? null;
  const tally = overview.data?.levels ?? ({} as Record<Level, number>);
  const maxHour = useMemo(
    () => Math.max(1, ...(series.data?.points ?? []).map((p) => p.max_score)),
    [series.data],
  );

  const runSweep = async () => {
    setBusy(true);
    try {
      const res = (await api.sweep(true)) as { evaluated: number; created: number; escalated: Record<string, unknown>[] };
      toast(
        res.created
          ? `Sweep done: ${res.evaluated} wards evaluated, ${res.created} new warning(s) issued.`
          : `Sweep done: ${res.evaluated} wards evaluated, nothing crossed a threshold.`,
        res.created ? "info" : "success",
      );
      await overview.reload();
      await analytics.reload();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Kpi label="Population covered" value={compactNumber(analytics.data?.population_covered ?? 0)} sub={`${analytics.data?.wards ?? 0} wards · ${analytics.data?.districts ?? 0} districts`} />
        <Kpi
          label="Exposed right now"
          value={compactNumber(analytics.data?.population_exposed ?? 0)}
          sub={`${tally.orange ?? 0} orange · ${tally.red ?? 0} red`}
          tone="#f97316"
        />
        <Kpi label="Warnings in 24 h" value={String(analytics.data?.alerts_24h ?? 0)} sub={`${analytics.data?.open_reports ?? 0} reports awaiting triage`} />
        <Kpi
          label="Median lead time"
          value={
            analytics.data?.median_lead_minutes === null || analytics.data?.median_lead_minutes === undefined
              ? "no pairs yet"
              : `${analytics.data.median_lead_minutes} min`
          }
          sub="warning before first ground report"
          tone="#22c55e"
        />
        <Kpi label="Mean confidence" value={`${Math.round((analytics.data?.mean_confidence ?? 0) * 100)}%`} sub={`telemetry: ${analytics.data?.telemetry_source ?? "—"}`} />
      </div>

      <div className="grid lg:grid-cols-[1.5fr_1fr] gap-4 items-start">
        <div className="ops-panel overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <div>
              <p className="text-white text-[14px] font-bold">Ward risk map</p>
              <p className="text-ink-400 text-[11px]">Pulse marks a live escalation</p>
            </div>
            <button className="btn btn-sm bg-white/10 text-white hover:bg-white/18" onClick={runSweep} disabled={busy}>
              <RefreshCw size={13} className={busy ? "animate-spin" : ""} /> {busy ? "Sweeping…" : "Run sweep"}
            </button>
          </div>
          <div className="h-[420px] bg-ink-900">
            <RiskMap wards={wards} selectedCode={selected} onSelectWard={setSelected} height="100%" />
          </div>
          {chosen && (
            <div className="px-4 py-3.5 border-t border-white/10">
              <div className="flex items-center justify-between gap-3 mb-3">
                <div className="min-w-0">
                  <p className="text-white text-[13px] font-bold truncate">{chosen.name}</p>
                  <p className="text-ink-400 text-[11px]">
                    {chosen.district} · {formatNumber(chosen.population)} residents · score{" "}
                    <span style={{ color: LEVEL_COLOR[chosen.level] }}>{Math.round(chosen.score)}</span>
                  </p>
                </div>
                <LevelBadge level={chosen.level} />
              </div>
              <div className="ops-panel p-3">
                <p className="ops-label mb-2">Contribution by factor</p>
                <div className="[&_summary]:!text-white [&_.text-ink-900]:!text-ink-100 [&_.text-ink-400]:!text-ink-400 [&_.text-ink-600]:!text-ink-300 [&_.bg-white]:!bg-white/5 [&_.border-\\[var\\(--line\\)\\]]:!border-white/10 [&_.bg-ink-100\\/40]:!bg-white/5">
                  <FactorBreakdown factors={chosen.factors.slice(0, 5)} level={chosen.level} compact />
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="grid gap-4 content-start">
          <div className="ops-panel p-4">
            <p className="text-white text-[13px] font-bold mb-1">Mean risk, last 24 h</p>
            <p className="text-ink-400 text-[11px] mb-3">Peak reaches {Math.round(maxHour)} at the worst hour.</p>
            <div className="h-[130px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series.data?.points ?? []} margin={{ top: 4, right: 0, bottom: 0, left: -28 }}>
                  <defs>
                    <linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f97316" stopOpacity={0.6} />
                      <stop offset="100%" stopColor="#f97316" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="hour" tick={{ fontSize: 8, fill: "#5b6b86" }} interval={4} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 8, fill: "#5b6b86" }} tickLine={false} axisLine={false} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{ background: "#0b1220", border: "1px solid rgba(255,255,255,.12)", borderRadius: 10, fontSize: 11 }}
                    labelStyle={{ color: "#c3d0e4" }}
                  />
                  <Area type="monotone" dataKey="mean_score" stroke="#f97316" strokeWidth={2} fill="url(#riskFill)" name="mean" />
                  <Area type="monotone" dataKey="max_score" stroke="#dc2626" strokeWidth={1.5} fill="transparent" name="worst ward" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="ops-panel p-4">
            <p className="text-white text-[13px] font-bold mb-3">Level distribution</p>
            <div className="h-[110px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={(["green", "blue", "yellow", "orange", "red"] as Level[]).map((l) => ({
                    level: l,
                    wards: tally[l] ?? 0,
                  }))}
                  margin={{ top: 0, right: 0, bottom: 0, left: -30 }}
                >
                  <XAxis dataKey="level" tick={{ fontSize: 9, fill: "#8ea0bd" }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 9, fill: "#8ea0bd" }} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid rgba(255,255,255,.12)", borderRadius: 8, fontSize: 11 }} />
                  <Bar dataKey="wards" radius={[4, 4, 0, 0]}>
                    {(["green", "blue", "yellow", "orange", "red"] as Level[]).map((l) => (
                      <Cell key={l} fill={LEVEL_COLOR[l]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="ops-panel p-4">
            <p className="text-white text-[13px] font-bold mb-3">District exposure</p>
            <div className="grid gap-2">
              {(coverage.data?.districts ?? []).slice(0, 6).map((d: CoverageRow) => (
                <div key={d.district} className="flex items-center gap-2.5">
                  <span className="text-[11px] text-ink-300 w-28 truncate shrink-0">{d.district}</span>
                  <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.min(100, (d.exposed / Math.max(1, coverage.data?.districts?.[0]?.exposed ?? 1)) * 100)}%`,
                        background: LEVEL_COLOR[d.worst_level],
                      }}
                    />
                  </div>
                  <span className="text-[10px] font-mono text-ink-400 w-14 text-right shrink-0 tabular">
                    {compactNumber(d.exposed)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="ops-panel">
        <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
          <p className="text-white text-[13px] font-bold">Highest-risk wards</p>
          <span className="text-ink-400 text-[11px]">as of {timeAgo(overview.data?.as_of, now)}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="text-[10px] uppercase tracking-widest text-ink-400">
                {["Ward", "District", "Score", "Level", "Rain 24 h", "Exposed", "Confidence", "Top driver"].map((h) => (
                  <th key={h} className="px-4 py-2 font-bold whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {wards.slice(0, 10).map((w: WardRiskSummary) => {
                const top = [...w.factors].sort((a, b) => b.contribution - a.contribution)[0];
                return (
                  <tr
                    key={w.code}
                    onClick={() => setSelected(w.code)}
                    className="border-t border-white/[0.07] hover:bg-white/[0.04] cursor-pointer text-[12px]"
                  >
                    <td className="px-4 py-2.5 font-semibold text-white whitespace-nowrap">{w.name}</td>
                    <td className="px-4 py-2.5 text-ink-300 whitespace-nowrap">{w.district}</td>
                    <td className="px-4 py-2.5 font-bold tabular" style={{ color: LEVEL_COLOR[w.level] }}>
                      {Math.round(w.score)}
                    </td>
                    <td className="px-4 py-2.5">
                      <LevelBadge level={w.level} size="sm" />
                    </td>
                    <td className="px-4 py-2.5 text-ink-300 tabular">{w.inputs.rain_24h_mm} mm</td>
                    <td className="px-4 py-2.5 text-ink-300 tabular">{compactNumber(w.population_at_risk)}</td>
                    <td className="px-4 py-2.5 text-ink-400 tabular">{Math.round(w.confidence * 100)}%</td>
                    <td className="px-4 py-2.5 text-ink-300 whitespace-nowrap">{top?.label}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {reports.data?.reports?.length ? (
        <div className="ops-panel">
          <div className="px-4 py-3 border-b border-white/10">
            <p className="text-white text-[13px] font-bold">Unverified ground reports</p>
            <p className="text-ink-400 text-[11px]">
              These raise the crowd-corroboration multiplier once a responder confirms them.
            </p>
          </div>
          <ul>
            {reports.data.reports.map((r: HazardReport) => (
              <li key={r.code} className="px-4 py-2.5 border-t border-white/[0.07] flex items-center gap-3 text-[12px]">
                <span className="w-1.5 h-1.5 rounded-full bg-risk-orange shrink-0" />
                <span className="text-white font-semibold truncate flex-1">{r.title || r.hazard_type}</span>
                <span className="text-ink-400 shrink-0">{r.ward_name}</span>
                <span className="text-ink-400 shrink-0 tabular">{Math.round(r.confidence * 100)}%</span>
                <span className="text-ink-400 shrink-0">{timeAgo(r.created_at, now)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="ops-panel p-3.5">
      <p className="ops-label">{label}</p>
      <p className="ops-value mt-1.5" style={tone ? { color: tone } : undefined}>
        {value}
      </p>
      {sub && <p className="text-[10px] text-ink-400 mt-1.5 leading-snug">{sub}</p>}
    </div>
  );
}

/* ------------------------------------------------------------- warnings */

function WarningsTab() {
  const toast = useToast();
  const { user } = useSession();
  const [wardCode, setWardCode] = useState("PKR-RNK");
  const [level, setLevel] = useState<Level>("orange");
  const [hazard, setHazard] = useState("landslide");
  const [channels, setChannels] = useState<string[]>(["sms", "ivr"]);
  const [ttl, setTtl] = useState(120);
  const [preview, setPreview] = useState<Record<string, { subject: string; sms: string; ivr: string }> | null>(null);
  const [reach, setReach] = useState<{ real_recipients: number; estimated_reach: number } | null>(null);
  const [busy, setBusy] = useState<"preview" | "send" | null>(null);

  const wards = useAsync(() => api.overview(), []);
  const alerts = useAsync(() => api.alerts({ limit: 25 }), []);
  const ward = (wards.data?.wards ?? []).find((w) => w.code === wardCode);

  const doPreview = async () => {
    setBusy("preview");
    try {
      const res = (await api.previewAlert({ ward_code: wardCode, level, hazard_type: hazard, broadcast: false })) as {
        messages: Record<string, { subject: string; sms: string; ivr: string }>;
        real_recipients: number;
        estimated_reach: number;
      };
      setPreview(res.messages);
      setReach({ real_recipients: res.real_recipients, estimated_reach: res.estimated_reach });
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };

  const doSend = async () => {
    if (!window.confirm(`Broadcast a ${level.toUpperCase()} warning to ${ward?.name ?? wardCode}? This dispatches to every subscriber in that ward.`)) return;
    setBusy("send");
    try {
      const alert = await api.createAlert({
        ward_code: wardCode,
        level,
        hazard_type: hazard,
        channels,
        ttl_minutes: ttl,
        broadcast: true,
      });
      toast(`${alert.code} issued and broadcast.`, "success");
      setBusy(null);
      await alerts.reload();
    } catch (e) {
      toast((e as Error).message, "error");
      setBusy(null);
    }
  };

  return (
    <div className="grid lg:grid-cols-[1fr_1fr] gap-4 items-start">
      <div className="ops-panel p-4">
        <p className="text-white text-[14px] font-bold mb-1">Author a warning</p>
        <p className="text-ink-400 text-[11px] mb-4 leading-relaxed">
          Manual warnings are attributed to your account ({user?.full_name}) and appear in the audit trail separately
          from automatic escalations, so an after-action review can tell them apart.
        </p>

        <label className="ops-label block mb-1.5">Ward</label>
        <select className="select !bg-white/10 !border-white/15 !text-white mb-3" value={wardCode} onChange={(e) => setWardCode(e.target.value)}>
          {(wards.data?.wards ?? []).map((w) => (
            <option key={w.code} value={w.code} className="text-ink-900">
              {w.district} — {w.name} ({Math.round(w.score)})
            </option>
          ))}
        </select>

        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="ops-label block mb-1.5">Level</label>
            <div className="flex gap-1">
              {(["yellow", "orange", "red"] as Level[]).map((l) => (
                <button
                  key={l}
                  onClick={() => setLevel(l)}
                  className="flex-1 py-2 rounded-lg text-[10px] font-bold uppercase transition-all"
                  style={
                    level === l
                      ? { background: LEVEL_COLOR[l], color: "#fff" }
                      : { background: "rgba(255,255,255,.07)", color: "#8ea0bd" }
                  }
                >
                  {l}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="ops-label block mb-1.5">Hazard</label>
            <select className="select !bg-white/10 !border-white/15 !text-white" value={hazard} onChange={(e) => setHazard(e.target.value)}>
              {["landslide", "flash_flood", "debris_flow", "cloudburst", "road_block"].map((h) => (
                <option key={h} value={h} className="text-ink-900">
                  {h.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>
        </div>

        <label className="ops-label block mb-1.5">Channels</label>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {["sms", "ivr", "inapp"].map((c) => {
            const on = channels.includes(c);
            return (
              <button
                key={c}
                onClick={() => setChannels((p) => (on ? p.filter((x) => x !== c) : [...p, c]))}
                className="px-3 py-1.5 rounded-lg text-[11px] font-bold uppercase transition-all"
                style={
                  on
                    ? { background: "#0ea5e9", color: "#fff" }
                    : { background: "rgba(255,255,255,.07)", color: "#8ea0bd" }
                }
              >
                {c === "ivr" ? "voice call" : c}
              </button>
            );
          })}
        </div>

        <label className="ops-label block mb-1.5">Expires after {ttl} min</label>
        <input
          type="range"
          min={15}
          max={720}
          step={15}
          value={ttl}
          onChange={(e) => setTtl(+e.target.value)}
          className="w-full accent-sky-500 mb-4"
        />

        <div className="flex gap-2">
          <button className="btn-ghost flex-1 !bg-white/10 !text-white !border-white/15 hover:!bg-white/18" onClick={doPreview} disabled={!!busy}>
            <Bell size={15} /> {busy === "preview" ? "Rendering…" : "Preview all languages"}
          </button>
          <button className="btn-danger flex-1" onClick={doSend} disabled={!!busy}>
            <Send size={15} /> {busy === "send" ? "Broadcasting…" : "Issue & broadcast"}
          </button>
        </div>
        <p className="text-[10px] text-ink-400 mt-3 leading-relaxed">
          Voice calls are only placed at orange and red. They cost real money per minute and are the right tool for a
          household with no literate phone user — not for every advisory.
        </p>
      </div>

      <div className="grid gap-4 content-start">
        {preview && (
          <div className="ops-panel p-4 animate-slide">
            <p className="text-white text-[13px] font-bold mb-1">Exactly what each language group receives</p>
            <p className="text-ink-400 text-[11px] mb-3">
              {reach?.real_recipients ?? 0} registered subscribers · {formatNumber(reach?.estimated_reach ?? 0)} phones
              in the ward
            </p>
            <div className="grid gap-3">
              {Object.entries(preview).map(([lang, msg]) => (
                <div key={lang} className="rounded-xl bg-white/5 border border-white/10 p-3">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-ink-400 mb-1.5">
                    {lang === "gar" ? "Garhwali" : lang === "hi" ? "Hindi" : "English"}
                  </p>
                  <p className={`${lang === "en" ? "" : "deva"} text-[12px] text-white leading-relaxed`}>{msg.sms}</p>
                  <p className={`${lang === "en" ? "" : "deva"} text-[11px] text-ink-300 leading-relaxed mt-2 pt-2 border-t border-white/10`}>
                    <span className="font-bold text-ink-400">IVR script: </span>
                    {msg.ivr}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="ops-panel">
          <p className="text-white text-[13px] font-bold px-4 py-3 border-b border-white/10">Warnings out</p>
          <ul className="max-h-[320px] overflow-y-auto">
            {(alerts.data?.alerts ?? []).map((a) => (
              <li key={a.code} className="px-4 py-3 border-b border-white/[0.07] last:border-0">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold text-white truncate">{a.title}</p>
                    <p className="text-[10px] text-ink-400 mt-0.5">
                      {a.code} · {a.auto_issued ? "automatic" : "manual"} · {timeAgo(a.issued_at)} ·{" "}
                      {a.status}
                    </p>
                  </div>
                  <LevelBadge level={a.level} size="sm" />
                </div>
                <div className="flex gap-3 mt-2 text-[10px] text-ink-400 tabular">
                  <span>reached {formatNumber(a.delivered)}</span>
                  <span>of {formatNumber(a.reach_target)}</span>
                  <span>{a.acknowledged} acks</span>
                  <button
                    className="ml-auto text-sky-400 hover:underline"
                    onClick={async () => {
                      try {
                        await api.setAlertStatus(a.code, "revoked");
                        toast(`${a.code} revoked.`, "info");
                        await alerts.reload();
                      } catch (e) {
                        toast((e as Error).message, "error");
                      }
                    }}
                  >
                    revoke
                  </button>
                </div>
              </li>
            ))}
            {!alerts.data?.alerts.length && <li className="px-4 py-6 text-[12px] text-ink-400">No warnings in the last 72 h.</li>}
          </ul>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- drill */

function DrillTab() {
  const toast = useToast();
  const [wardCode, setWardCode] = useState("DEH-KTB");
  const [rain1h, setRain1h] = useState(90);
  const [rain24h, setRain24h] = useState(190);
  const [rain72h, setRain72h] = useState(320);
  const [forecast, setForecast] = useState(65);
  const [soil, setSoil] = useState(0.9);
  const [broadcast, setBroadcast] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);

  const wards = useAsync(() => api.overview(), []);
  const list = wards.data?.wards ?? [];
  const current = list.find((w) => w.code === wardCode);

  const presets = [
    { name: "Dry season baseline", r1: 0, r24: 2, r72: 5, f: 0, s: 0.15 },
    { name: "Saturated ground, light rain", r1: 6, r24: 45, r72: 210, f: 8, s: 0.85 },
    { name: "Cloudburst on dry slope", r1: 95, r24: 100, r72: 110, f: 12, s: 0.4 },
    { name: "Ranikhot 2021 replay", r1: 78, r24: 210, r72: 340, f: 55, s: 0.94 },
  ];

  const run = async () => {
    setBusy(true);
    try {
      const res = await api.scenario({
        ward_code: wardCode,
        rain_1h_mm: rain1h,
        rain_24h_mm: rain24h,
        rain_72h_mm: rain72h,
        forecast_6h_mm: forecast,
        soil_moisture: soil,
        broadcast,
      });
      setResult(res.ward);
      toast("Scenario applied — telemetry tagged as a drill, not an observation.", "info");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const level = (result?.level ?? current?.level) as Level | undefined;

  return (
    <div className="grid lg:grid-cols-[1fr_1.1fr] gap-4 items-start">
      <div className="ops-panel p-4">
        <p className="text-white text-[14px] font-bold mb-1 flex items-center gap-2">
          <FlaskConical size={15} /> What-if and pre-monsoon drill
        </p>
        <p className="text-ink-400 text-[11px] mb-4 leading-relaxed">
          Inject a rain profile for one ward and watch the score, the factor waterfall and the escalation logic react.
          Nothing here touches a sensor, and unless broadcast is on nobody is messaged. This is also the tool for the
          annual mock drill the district is required to run.
        </p>

        <label className="ops-label block mb-1.5">Preset</label>
        <div className="grid grid-cols-2 gap-1.5 mb-4">
          {presets.map((p) => (
            <button
              key={p.name}
              onClick={() => {
                setRain1h(p.r1);
                setRain24h(p.r24);
                setRain72h(p.r72);
                setForecast(p.f);
                setSoil(p.s);
              }}
              className="text-left px-2.5 py-2 rounded-lg text-[11px] font-semibold bg-white/5 hover:bg-white/10 text-ink-200 border border-white/10"
            >
              {p.name}
            </button>
          ))}
        </div>

        <label className="ops-label block mb-1.5">Ward</label>
        <select
          className="select !bg-white/10 !border-white/15 !text-white mb-4"
          value={wardCode}
          onChange={(e) => setWardCode(e.target.value)}
        >
          {list.map((w) => (
            <option key={w.code} value={w.code} className="text-ink-900">
              {w.district} — {w.name} · now {Math.round(w.score)}
            </option>
          ))}
        </select>

        {[
          { label: "Rain, last hour (mm)", v: rain1h, set: setRain1h, max: 200 },
          { label: "Rain, 24 h (mm)", v: rain24h, set: setRain24h, max: 400 },
          { label: "Rain, 72 h (mm)", v: rain72h, set: setRain72h, max: 600 },
          { label: "Forecast, next 6 h (mm)", v: forecast, set: setForecast, max: 200 },
          { label: "Soil saturation", v: Math.round(soil * 100), set: (x: number) => setSoil(x / 100), max: 100, suffix: "%" },
        ].map((s) => (
          <div key={s.label} className="mb-3">
            <div className="flex justify-between text-[11px] mb-1">
              <span className="text-ink-300">{s.label}</span>
              <span className="font-mono text-white tabular">
                {s.suffix ? `${s.v}${s.suffix}` : s.v}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={s.max}
              value={s.suffix ? s.v : s.v}
              onChange={(e) => s.set(+e.target.value)}
              className="w-full accent-orange-500"
            />
          </div>
        ))}

        <label className="flex items-center gap-2 text-[11px] text-ink-300 mt-3 cursor-pointer">
          <input type="checkbox" className="w-4 h-4 accent-red-600" checked={broadcast} onChange={(e) => setBroadcast(e.target.checked)} />
          Actually run the escalation path (sends to subscribers)
        </label>

        <button className="btn-primary w-full mt-4 !bg-risk-orange" onClick={run} disabled={busy}>
          <Play size={15} /> {busy ? "Running…" : "Run scenario"}
        </button>
      </div>

      <div className="grid gap-4 content-start">
        <div className="ops-panel p-4">
          <div className="flex items-start justify-between gap-3 mb-3">
            <div>
              <p className="ops-label">Result</p>
              <p className="text-white text-[15px] font-bold mt-1">{(result?.name as string) ?? current?.name}</p>
            </div>
            {level && (
              <div className="text-right">
                <p className="text-3xl font-extrabold tabular" style={{ color: LEVEL_COLOR[level] }}>
                  {Math.round(Number(result?.score ?? current?.score ?? 0))}
                </p>
                <LevelBadge level={level} size="sm" />
              </div>
            )}
          </div>
          {current && !result && (
            <p className="text-ink-400 text-[11px]">
              Baseline before you run anything: score {Math.round(current.score)} ({current.level}), rain{" "}
              {current.inputs.rain_24h_mm} mm/24 h, confidence {Math.round(current.confidence * 100)}%.
            </p>
          )}
          {result && (
            <div className="grid grid-cols-3 gap-2 mt-2">
              {[
                ["Probability 24 h", `${Math.round((Number(result.probability_24h) || 0) * 100)}%`],
                ["Exposed", compactNumber(Number(result.population_at_risk) || 0)],
                ["Crowd uplift", `×${Number(result.crowd_uplift ?? 1).toFixed(2)}`],
              ].map(([l, v]) => (
                <div key={l} className="rounded-lg bg-white/5 p-2.5">
                  <p className="ops-label">{l}</p>
                  <p className="text-white text-[15px] font-bold tabular mt-1">{v}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {result && (
          <div className="ops-panel p-4">
            <p className="text-white text-[13px] font-bold mb-3">What moved the score</p>
            <div className="[&_.bg-white]:!bg-white/5 [&_summary]:!text-white [&_.text-ink-900]:!text-ink-100 [&_.text-ink-400]:!text-ink-400 [&_.text-ink-600]:!text-ink-300 [&_.border-\\[var\\(--line\\)\\]]:!border-white/10">
              <FactorBreakdown
                factors={(result.factors as WardRiskSummary["factors"]) ?? []}
                level={(result.level as Level) ?? "yellow"}
                compact
              />
            </div>
          </div>
        )}

        <p className="text-[11px] text-ink-400 leading-relaxed px-1">
          Every scenario write is stored with <code className="font-mono text-ink-300">source='scenario'</code>, so a
          later review can separate a drill from a real event. That distinction is the difference between a tool an
          administration will trust and one it will switch off after two false alarms.
        </p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- delivery */

function DeliveryTab() {
  const toast = useToast();
  const stats = useAsync(() => api.deliveryStats(), []);
  const rows = useAsync(() => api.notifications({ limit: 40 }), []);
  const d = stats.data;

  return (
    <div className="grid gap-4">
      <div className="ops-panel p-4">
        <p className="text-white text-[14px] font-bold mb-1">Delivery proof, not delivery claims</p>
        <p className="text-ink-400 text-[11px] leading-relaxed">
          Every dispatch is written to the ledger with its provider response. {d?.note ?? ""}
        </p>
        {d?.simulated && (
          <div className="mt-3 rounded-xl border border-risk-yellow/40 bg-risk-yellow/10 px-3.5 py-2.5">
            <p className="text-[12px] text-ink-100 leading-relaxed">
              <strong>Console provider active.</strong> These messages were not sent. Set{" "}
              <code className="font-mono text-[11px]">SMS_PROVIDER=twilio</code> (or{" "}
              <code className="font-mono text-[11px]">msg91</code>) with credentials for real delivery — the adapters
              are already implemented.
            </p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi label="Provider" value={d?.provider ?? "—"} sub={d?.simulated ? "simulating" : "live"} />
        <Kpi label="Messages logged" value={formatNumber(d?.total ?? 0)} />
        <Kpi label="Accepted by provider" value={formatNumber(d?.by_status?.sent ?? 0)} tone="#22c55e" />
        <Kpi label="Recorded as simulated" value={formatNumber(d?.by_status?.simulated ?? 0)} tone="#ca8a04" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="ops-panel p-4">
          <p className="text-white text-[13px] font-bold mb-3">By language</p>
          <p className="text-ink-400 text-[11px] mb-3 leading-relaxed">
            Language is resolved per recipient from their subscription, not from the sender's choice — a Garhwali
            household gets the Garhwali script.
          </p>
          <div className="grid gap-2">
            {Object.entries(d?.by_lang ?? ({} as Record<string, number>)).map(([lang, n]) => (
              <div key={lang} className="flex items-center gap-2.5">
                <span className="text-[11px] text-ink-300 w-20 shrink-0">
                  {lang === "hi" ? "Hindi" : lang === "gar" ? "Garhwali" : "English"}
                </span>
                <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className="h-full bg-sky-500"
                    style={{ width: `${Math.min(100, ((n as number) / Math.max(1, d?.total ?? 1)) * 100)}%` }}
                  />
                </div>
                <span className="text-[11px] font-mono text-ink-400 w-12 text-right tabular">{n}</span>
              </div>
            ))}
            {!d?.total && <p className="text-[11px] text-ink-400">Nothing dispatched yet.</p>}
          </div>
          <div className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-white/10">
            {Object.entries(d?.by_channel ?? ({} as Record<string, number>)).map(([c, n]) => (
              <div key={c}>
                <p className="ops-label">{c === "ivr" ? "voice" : c}</p>
                <p className="text-white text-[15px] font-bold tabular mt-0.5">{n}</p>
              </div>
            ))}
          </div>
          <button
            className="btn-ghost w-full mt-4 !bg-white/10 !text-white !border-white/15"
            onClick={async () => {
              try {
                const res = (await api.testNotify()) as { status: string; body_preview: string };
                toast(`Test message ${res.status}: ${res.body_preview}`, "info");
                await stats.reload();
              } catch (e) {
                toast((e as Error).message, "error");
              }
            }}
          >
            <Gauge size={14} /> Send a test to my own number
          </button>
        </div>

        <div className="ops-panel overflow-hidden">
          <p className="text-white text-[13px] font-bold px-4 py-3 border-b border-white/10">Last dispatches</p>
          <div className="max-h-[420px] overflow-y-auto">
            {(rows.data?.notifications ?? []).map((n) => (
              <div key={String(n.id)} className="px-4 py-2.5 border-b border-white/[0.07] last:border-0">
                <div className="flex items-center gap-2 text-[10px]">
                  <span className="font-mono text-ink-400">{n.phone}</span>
                  <span className="chip !text-[9px] !py-0" style={{ background: n.status === "sent" ? "#16a34a22" : "#ca8a0422", color: n.status === "sent" ? "#4ade80" : "#fbbf24" }}>
                    {n.status}
                  </span>
                  <span className="text-ink-400 ml-auto">
                    {n.channel} · {n.lang}
                  </span>
                </div>
                <p className={`${n.lang === "en" ? "" : "deva"} text-[11px] text-ink-200 mt-1 leading-snug`}>{n.body}</p>
              </div>
            ))}
            {!rows.data?.notifications.length && (
              <p className="px-4 py-6 text-[12px] text-ink-400">No dispatch recorded yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- audit */

function AuditTab() {
  const audit = useAsync(() => api.audit({ limit: 80 }), []);
  return (
    <div className="ops-panel overflow-hidden">
      <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
        <div>
          <p className="text-white text-[13px] font-bold">Audit trail</p>
          <p className="text-ink-400 text-[11px]">
            Who issued what, who verified what, who changed the model. Append-only.
          </p>
        </div>
        <span className="pill !bg-white/10 !border-white/15 !text-ink-300">{audit.data?.entries.length ?? 0} events</span>
      </div>
      <table className="w-full text-left">
        <thead>
          <tr className="text-[10px] uppercase tracking-widest text-ink-400">
            {["When", "Actor", "Action", "Entity", "Detail"].map((h) => (
              <th key={h} className="px-4 py-2 font-bold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(audit.data?.entries ?? []).map((e) => (
            <tr key={e.id} className="border-t border-white/[0.07] text-[11px] align-top">
              <td className="px-4 py-2 text-ink-400 whitespace-nowrap">{new Date(e.created_at).toLocaleString("en-IN")}</td>
              <td className="px-4 py-2 text-white font-semibold whitespace-nowrap">{e.actor_label}</td>
              <td className="px-4 py-2">
                <span className="font-mono text-sky-300">{e.action}</span>
              </td>
              <td className="px-4 py-2 text-ink-300">
                {e.entity} <span className="text-ink-400 font-mono">{e.entity_id}</span>
              </td>
              <td className="px-4 py-2 text-ink-400 font-mono break-all max-w-[22rem]">
                {Object.keys(e.detail ?? {}).length ? JSON.stringify(e.detail) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!audit.data?.entries.length && <p className="px-4 py-6 text-[12px] text-ink-400">Nothing recorded yet.</p>}
    </div>
  );
}
