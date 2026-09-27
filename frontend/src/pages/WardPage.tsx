import { ArrowLeft, Bell, BellOff, Clock, Hospital, Mountain, Route, School, ShieldAlert, TriangleAlert, Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Card, ErrorState, LEVEL_COLOR, Loading, SkeletonRows, compactNumber, formatNumber, isHigh, timeAgo, useToast } from "../components/ui";
import { FactorBreakdown, RainChart, ReportRow, WardSummary } from "../components/briefing";
import { useAsync, useGeolocate } from "../hooks";
import { useLive } from "../state/live";

const LITH_LABEL: Record<string, string> = {
  siwalik: "Siwalik group — young, unconsolidated sandstone and shale; the most failure-prone unit in the outer hills",
  lesser_himalaya: "Lesser Himalaya — sheared phyllite, slate and quartzite bounded by major thrusts",
  greater_himalaya: "Greater Himalaya Crystalline — gneiss and granite, competent but heavily jointed",
  tethys_himalaya: "Tethys Himalaya — sedimentary cover north of the Main Tibetan Thrust",
  alluvium: "Alluvium — unconsolidated valley fill, prone to scour and bank collapse",
  granite_gneiss: "Granite / gneiss massif",
};

export default function WardPage() {
  const { code = "" } = useParams();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const toast = useToast();
  const { revision } = useLive();
  const { coords } = useGeolocate();
  const [busy, setBusy] = useState(false);

  const ward = useAsync(() => api.ward(code), [code, revision]);
  const history = useAsync(() => api.history(code), [code, revision]);
  const subs = useAsync(() => api.subscriptions().catch(() => []), []);

  const data = ward.data;
  const subscribed = (subs.data ?? []).some((s) => s.ward_code === code);

  const toggleSubscribe = async () => {
    setBusy(true);
    try {
      if (subscribed) {
        await api.unsubscribe(code);
        toast(`Stopped warnings for ${data?.name}.`, "info");
      } else {
        const res = (await api.subscribe(code, {
          channel: "sms",
          lang: i18n.language === "gar" ? "gar" : i18n.language === "hi" ? "hi" : "en",
        })) as { message?: string };
        toast(res.message ?? `You will get warnings for ${data?.name} by SMS.`, "success");
      }
      await subs.reload();
    } catch (e) {
      const msg = (e as Error).message;
      toast(/sign in|authenticated/i.test(msg) ? "Sign in first to receive warnings for this ward." : msg, "error");
      if (/sign in|authenticated/i.test(msg)) navigate("/signin");
    } finally {
      setBusy(false);
    }
  };

  if (ward.loading && !data) return <Loading label={`Loading ${code}…`} />;
  if (ward.error) return <ErrorState error={ward.error} onRetry={ward.reload} />;
  if (!data) return null;

  const distance = coords ? geoDistance(coords.lat, coords.lng, data.latitude, data.longitude) : null;
  const points = (history.data?.points ?? []).map((p) => Number(p.score ?? 0));

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button className="btn-ghost btn-sm" onClick={() => navigate(-1)}>
          <ArrowLeft size={14} /> Back
        </button>
        <div className="flex items-center gap-2">
          <span className="pill tabular">
            <Clock size={12} /> recomputed {timeAgo(ward.data ? new Date().toISOString() : null)}
          </span>
          <button
            className={subscribed ? "btn-ghost" : "btn-primary"}
            onClick={toggleSubscribe}
            disabled={busy}
            title="Warnings for this ward reach you by SMS in your language"
          >
            {subscribed ? <BellOff size={15} /> : <Bell size={15} />}
            {subscribed ? "Stopping…" : "Alert me for this ward"}
          </button>
        </div>
      </div>

      {/* --------------------------------------------------------- score head */}
      <section className="panel overflow-hidden">
        <div className="h-1.5" style={{ background: LEVEL_COLOR[data.level] }} />
        <div className="p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
            <div className="min-w-0">
              <p className="eyebrow">{data.district} · ward {data.code}</p>
              <h1 className="text-2xl sm:text-[28px] leading-tight mt-1">{data.name}</h1>
              {data.name_hi && (
                <p className="deva text-[15px] text-ink-600 mt-0.5" lang="hi">
                  {data.name_hi}
                </p>
              )}
              <p className="text-[12px] text-ink-400 mt-1.5">
                {formatNumber(data.population)} residents · {formatNumber(data.registered_phones)} reachable phones ·{" "}
                {data.connectivity} connectivity
                {distance !== null && ` · ${distance.toFixed(1)} km from you`}
              </p>
            </div>
            {isHigh(data.level) && (
              <div
                className="rounded-xl px-4 py-3 max-w-sm flex gap-3 items-start"
                style={{ background: `${LEVEL_COLOR[data.level]}12`, border: `1px solid ${LEVEL_COLOR[data.level]}40` }}
              >
                <TriangleAlert size={18} style={{ color: LEVEL_COLOR[data.level] }} className="shrink-0 mt-0.5" />
                <div>
                  <p className="text-[12px] font-bold" style={{ color: LEVEL_COLOR[data.level] }}>
                    {t(`level.${data.level}`)}
                  </p>
                  <p className="text-[12px] text-ink-700 leading-snug mt-0.5">{t(`advice.${data.level}`)}</p>
                </div>
              </div>
            )}
          </div>

          {data.notes && (
            <p className="text-[12px] text-ink-600 leading-relaxed bg-ink-100/60 rounded-lg px-3.5 py-2.5 mb-4 border-l-2 border-risk-orange">
              {data.notes}
            </p>
          )}

          <WardSummary ward={data} />
        </div>
      </section>

      <div className="grid lg:grid-cols-[1.35fr_1fr] gap-5 items-start">
        {/* ------------------------------------------------------ explainability */}
        <div className="grid gap-5">
          <Card
            title="Why this score"
            subtitle="Ten weighted factors. Expand any row for the reasoning and the arithmetic."
          >
            <FactorBreakdown factors={data.factors} level={data.level} />
            <p className="text-[11px] text-ink-400 mt-4 leading-relaxed border-t border-[var(--line)] pt-3">
              Base total is multiplied by the crowd-corroboration factor (×{data.crowd_uplift.toFixed(2)}), capped at
              ×1.25, so several neighbours reporting the same crack can outrank a stale rain gauge but a single
              unverified message can never trigger an evacuation.{" "}
              <Link to="/model" className="underline">
                Read the full model card and its limits.
              </Link>
            </p>
          </Card>

          <Card title="Rainfall and forecast" subtitle="Observed hours plus the modelled forecast tail.">
            <RainChart series={data.rainfall_series} height={170} />
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4 pt-4 divider">
              <Mini label="Last hour" value={`${data.inputs.rain_1h_mm} mm`} />
              <Mini label="24 h total" value={`${data.inputs.rain_24h_mm} mm`} />
              <Mini label="72 h total" value={`${data.inputs.rain_72h_mm} mm`} />
              <Mini label="Next 6 h" value={`${data.inputs.forecast_6h_mm} mm`} tone="#f97316" />
            </div>
            <p className="text-[11px] text-ink-400 mt-3">
              {data.inputs.gauge_online
                ? `Live gauge reporting ${Math.round(data.inputs.telemetry_age_minutes ?? 0)} min ago.`
                : "No live gauge in this ward — rainfall is modelled from the gridded nowcast, which is why confidence is lower."}{" "}
              River stage proxy {data.inputs.river_level_m} m · soil saturation {Math.round(data.inputs.soil_moisture * 100)}%.
            </p>
          </Card>

          <Card
            title="Score over the last runs"
            subtitle="Every computation is persisted, so any warning can be replayed afterwards."
          >
            {points.length < 2 ? (
              <p className="text-[12px] text-ink-400">
                Not enough history yet — this fills in as the monitor loop runs.
              </p>
            ) : (
              <div className="flex items-end gap-1 h-24">
                {points.slice(-48).map((p, i) => (
                  <div
                    key={i}
                    className="flex-1 rounded-t-sm transition-all"
                    style={{ height: `${Math.max(4, p)}%`, background: LEVEL_COLOR[scoreToLevel(p)] }}
                    title={`score ${p.toFixed(1)}`}
                  />
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* --------------------------------------------------------- side stack */}
        <div className="grid gap-5 content-start">
          <Card title="Terrain and exposure" bodyClass="p-0">
            <ul className="divide-y divide-[var(--line)]">
              <Row Icon={Mountain} label="Slope angle" value={`${data.slope_deg.toFixed(0)}°`} />
              <Row Icon={Mountain} label="Elevation" value={`${formatNumber(data.elevation_m)} m`} />
              <Row
                Icon={Mountain}
                label="Rock type"
                value={data.lithology.replace(/_/g, " ")}
                sub={LITH_LABEL[data.lithology] ?? ""}
              />
              <Row Icon={Route} label="Riverside distance" value={`${data.river_distance_km} km`} />
              <Row Icon={TriangleAlert} label="Recorded past events" value={String(data.historical_events)} />
              <Row Icon={Users} label="Children / elderly" value={`${compactNumber(data.children)} / ${compactNumber(data.elderly)}`} />
              <Row Icon={School} label="Schools / health posts" value={`${data.schools} / ${data.health_centres}`} />
            </ul>
          </Card>

          <Card
            title="Nearest shelters"
            subtitle="Live free space, not just an address list."
            actions={
              <Link to="/shelters" className="btn-ghost btn-sm">
                All shelters
              </Link>
            }
            bodyClass="p-0"
          >
            {data.nearest_shelters.length === 0 && <SkeletonRows rows={2} height={52} />}
            <ul className="divide-y divide-[var(--line)]">
              {data.nearest_shelters.map((s) => (
                <li key={s.code} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold truncate">{s.name}</p>
                      <p className="text-[11px] text-ink-400">
                        {s.distance_km} km · bearing {s.bearing_deg}° · {s.capacity} capacity
                      </p>
                    </div>
                    <span
                      className="chip shrink-0"
                      style={{
                        background: s.free_places > 0 ? "#f0fdf4" : "#fef2f2",
                        color: s.free_places > 0 ? "#16a34a" : "#dc2626",
                      }}
                    >
                      {s.free_places > 0 ? `${s.free_places} free` : "full"}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {s.has_medical && (
                      <span className="pill !text-[10px]">
                        <Hospital size={10} /> medical
                      </span>
                    )}
                    {s.wheelchair_accessible && <span className="pill !text-[10px]">step-free</span>}
                    {s.manager_phone && (
                      <a
                        href={`tel:${s.manager_phone.replace(/[^\d+]/g, "")}`}
                        className="pill !text-[10px] !border-risk-blue/40 !text-risk-blue font-bold"
                      >
                        call officer
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Roads out of this ward" bodyClass="p-0" actions={<Link to="/roads" className="btn-ghost btn-sm">Network</Link>}>
            {data.roads.length === 0 ? (
              <p className="text-[12px] text-ink-400 px-4 py-3">No monitored segment touches this ward.</p>
            ) : (
              <ul className="divide-y divide-[var(--line)]">
                {data.roads.map((r) => (
                  <li key={r.code} className="px-4 py-2.5 flex items-center gap-3">
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ background: ROAD_COLOR[r.status] }}
                      title={r.status}
                    />
                    <span className="flex-1 min-w-0">
                      <span className="block text-[12px] font-semibold truncate">{r.name}</span>
                      <span className="block text-[10px] text-ink-400">
                        {r.length_km} km{r.is_lifeline ? " · lifeline" : ""}
                        {r.clearance_eta_hours ? ` · clears in ~${r.clearance_eta_hours} h` : ""}
                      </span>
                    </span>
                    <span className="text-[10px] font-bold uppercase tracking-wide shrink-0" style={{ color: ROAD_COLOR[r.status] }}>
                      {r.status}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="What residents are reporting"
            subtitle={`${data.inputs.open_reports} unverified · ${data.inputs.confirmed_reports} confirmed in the last 48 h`}
            actions={
              <Link to="/report" className="btn-primary btn-sm">
                <ShieldAlert size={13} /> Report
              </Link>
            }
            bodyClass="p-0"
          >
            {data.recent_reports.length === 0 ? (
              <p className="text-[12px] text-ink-400 px-4 py-4">
                Nothing filed in the last 72 hours. Reports from the ground are what sharpen a score like this one.
              </p>
            ) : (
              <div>
                {data.recent_reports.map((r) => (
                  <ReportRow key={r.code} report={r} />
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

const ROAD_COLOR: Record<string, string> = {
  open: "#16a34a",
  caution: "#ca8a04",
  partial: "#f97316",
  closed: "#dc2626",
};

function scoreToLevel(score: number) {
  if (score >= 76) return "red" as const;
  if (score >= 62) return "orange" as const;
  if (score >= 45) return "yellow" as const;
  if (score >= 25) return "blue" as const;
  return "green" as const;
}

function geoDistance(a: number, b: number, c: number, d: number) {
  const R = 6371;
  const toRad = (x: number) => (x * Math.PI) / 180;
  const h =
    Math.sin(toRad(c - a) / 2) ** 2 +
    Math.cos(toRad(a)) * Math.cos(toRad(c)) * Math.sin(toRad(d - b) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function Mini({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className="text-lg font-extrabold tabular mt-1" style={tone ? { color: tone } : undefined}>
        {value}
      </p>
    </div>
  );
}

function Row({
  Icon,
  label,
  value,
  sub,
}: {
  Icon: typeof Mountain;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <li className="px-4 py-2.5 flex items-start gap-3">
      <Icon size={14} className="text-ink-400 mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-[11px] text-ink-400 font-semibold uppercase tracking-wide">{label}</p>
        <p className="text-[13px] font-semibold text-ink-900 capitalize">{value}</p>
        {sub && <p className="text-[11px] text-ink-400 leading-snug mt-0.5">{sub}</p>}
      </div>
    </li>
  );
}
