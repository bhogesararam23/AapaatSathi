import { Crosshair, ExternalLink, MapPin, Navigation, ShieldAlert, Siren, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import type { Alert, Level, WardRiskSummary } from "../api/types";
import { Card, EmptyState, ErrorState, LEVEL_COLOR, LevelBadge, Loading, compactNumber, isHigh, timeAgo } from "../components/ui";
import { AlertBanner, FactorBreakdown, RainChart, WardSummary } from "../components/briefing";
import { RiskMap } from "../components/RiskMap";
import { useAsync, useGeolocate, useNow } from "../hooks";
import { useLive } from "../state/live";
import { useSession } from "../state/session";

const DISTRICTS = [
  { code: "", name: "All eight districts" },
  { code: "DEH", name: "Dehradun" },
  { code: "PKR", name: "Pauri Garhwal" },
  { code: "TEH", name: "Tehri" },
  { code: "UKD", name: "Uttarkashi" },
  { code: "CHM", name: "Chamoli" },
  { code: "RPR", name: "Rudraprayag" },
  { code: "ALM", name: "Almora" },
  { code: "NNT", name: "Nainital" },
];

/** Nearest ward by great-circle distance — good enough for a 1-2 km ward. */
function nearest(wards: WardRiskSummary[], lat: number, lng: number): WardRiskSummary | null {
  let best: WardRiskSummary | null = null;
  let bestD = Infinity;
  for (const w of wards) {
    const d = haversine(lat, lng, w.latitude, w.longitude);
    if (d < bestD) {
      bestD = d;
      best = w;
    }
  }
  return best;
}

function haversine(a: number, b: number, c: number, d: number) {
  const R = 6371;
  const toRad = (x: number) => (x * Math.PI) / 180;
  const dLat = toRad(c - a);
  const dLng = toRad(d - b);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a)) * Math.cos(toRad(c)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export default function Home() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { revision } = useLive();
  const { coords, status: geoStatus, locate } = useGeolocate();
  const { user } = useSession();
  const now = useNow();

  const [district, setDistrict] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const overview = useAsync(() => api.overview(district || undefined), [district, revision]);
  const alertsQ = useAsync(() => api.liveAlerts(), [revision], { intervalMs: 60_000 });

  const wards = overview.data?.wards ?? [];
  const ranked = useMemo(() => [...wards].sort((a, b) => b.score - a.score), [wards]);
  const mine = useMemo(
    () => (coords ? nearest(wards, coords.lat, coords.lng) : null),
    [coords, wards],
  );
  const shown = selected ? wards.find((w) => w.code === selected) ?? null : mine;
  const wardDetail = useAsync(() => (shown ? api.ward(shown.code) : Promise.resolve(null)), [shown?.code]);

  // Keep the selection valid when the district filter changes.
  useEffect(() => {
    if (selected && !wards.some((w) => w.code === selected)) setSelected(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [district]);

  const critical = wards.filter((w) => isHigh(w.level));
  const relevantAlerts: Alert[] = ((alertsQ.data?.alerts ?? []) as Alert[]).filter(
    (a) => !user?.district_id || a.district_id === user.district_id || !user,
  );

  return (
    <div className="grid gap-5">
      <AlertBanner alerts={relevantAlerts} />

      {/* ------------------------------------------------------- hero strip */}
      <section className="panel overflow-hidden">
        <div className="grid lg:grid-cols-[1.15fr_1fr]">
          <div className="p-5 sm:p-6 border-b lg:border-b-0 lg:border-r border-[var(--line)]">
            <p className="eyebrow flex items-center gap-1.5">
              <Siren size={12} className="text-risk-red" />
              Live ward susceptibility · {t("common.live")}
            </p>
            <h1 className="text-2xl sm:text-[28px] mt-2 leading-[1.15]">{t("hero.headline")}</h1>
            <p className="text-[14px] text-ink-600 mt-2 leading-relaxed max-w-xl">{t("hero.sub")}</p>

            <div className="flex flex-wrap items-center gap-2 mt-4">
              <button className="btn-primary" onClick={() => mine && navigate(`/ward/${mine.code}`)} disabled={!mine}>
                <Navigation size={15} />
                {mine ? `${t("hero.viewDetail")} — ${mine.name}` : t("hero.checking")}
              </button>
              <Link to="/report" className="btn-ghost">
                <ShieldAlert size={15} /> {t("report.title")}
              </Link>
              {geoStatus !== "granted" && (
                <button className="pill hover:bg-ink-100" onClick={locate} title="Share location so we can pick your ward">
                  <Crosshair size={12} />
                  {geoStatus === "denied" ? "Location blocked — tap to retry" : "Use my location"}
                </button>
              )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-5 divider">
              <Metric label="Wards watched" value={String(wards.length)} />
              <Metric label="At warning / evacuate" value={String(critical.length)} tone={critical.length ? "#dc2626" : undefined} />
              <Metric label="People exposed" value={compactNumber(overview.data?.population_exposed ?? 0)} />
              <Metric
                label="Model confidence"
                value={`${Math.round((overview.data?.mean_confidence ?? 0) * 100)}%`}
                hint="measured vs inferred"
              />
            </div>
          </div>

          {/* focused ward panel */}
          <div className="p-5 sm:p-6 bg-ink-100/40 min-h-[280px]">
            {!shown && (
              <EmptyState
                title={geoStatus === "denied" ? "Turn on location to see your ward" : "Pick a ward on the map"}
                hint="Tap any marker to read its full briefing, including why the score is what it is."
                icon={<MapPin size={18} />}
              />
            )}
            {shown && wardDetail.loading && <Loading label={`Loading ${shown.name}…`} />}
            {shown && wardDetail.error && <ErrorState error={wardDetail.error} onRetry={wardDetail.reload} compact />}
            {shown && wardDetail.data && (
              <div className="animate-slide">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <p className="eyebrow">{t("hero.yourRisk")}</p>
                    <h2 className="text-lg leading-tight truncate">{shown.name}</h2>
                    <p className="text-[11px] text-ink-400">
                      {shown.district}
                      {coords && ` · ${haversine(coords.lat, coords.lng, shown.latitude, shown.longitude).toFixed(1)} km from you`}
                    </p>
                  </div>
                  <Link to={`/ward/${shown.code}`} className="btn-ghost btn-sm shrink-0">
                    Full briefing <ExternalLink size={13} />
                  </Link>
                </div>
                <WardSummary ward={shown} />
                <div className="mt-4">
                  <FactorBreakdown factors={shown.factors.slice(0, 4)} level={shown.level} compact />
                </div>
                <div className="mt-4">
                  <RainChart series={shown ? wardDetail.data.rainfall_series : []} height={110} />
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- map + list */}
      <div className="grid lg:grid-cols-[1.6fr_1fr] gap-5">
        <Card
          bodyClass="p-0"
          title={
            <span className="flex items-center gap-2">
              Risk map
              <select
                className="select !w-auto !py-1 !text-xs !rounded-lg"
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
                aria-label="Filter by district"
              >
                {DISTRICTS.map((d) => (
                  <option key={d.code} value={d.code}>
                    {d.name}
                  </option>
                ))}
              </select>
            </span>
          }
          subtitle="Markers pulse where a warning is live. Colour is susceptibility, not certainty of failure."
          actions={<span className="pill tabular">{wards.length} wards</span>}
        >
          <div className="h-[420px] sm:h-[520px] relative">
            {overview.loading && !wards.length && (
              <div className="absolute inset-0 grid place-items-center bg-white/70 z-20">
                <Loading label="Fetching ward risk…" />
              </div>
            )}
            {overview.error && (
              <div className="p-4">
                <ErrorState error={overview.error} onRetry={overview.reload} />
              </div>
            )}
            <RiskMap
              wards={wards}
              selectedCode={shown?.code ?? null}
              onSelectWard={(code) => setSelected(code)}
              className="h-full w-full"
              height="100%"
            />
          </div>
        </Card>

        <div className="grid gap-5 content-start">
          <Card
            title="Highest risk right now"
            subtitle="Sorted by score. Click any ward to focus the map."
            bodyClass="p-0"
          >
            {ranked.length === 0 && !overview.loading && <EmptyState title="No wards scored yet" />}
            <div className="max-h-[360px] overflow-y-auto">
              {ranked.slice(0, 12).map((w) => (
                <button
                  key={w.code}
                  onClick={() => setSelected(w.code)}
                  className={`w-full text-left table-row grid-cols-[1fr_auto] hover:bg-ink-100 transition-colors ${
                    shown?.code === w.code ? "bg-ink-100" : ""
                  }`}
                >
                  <span className="min-w-0">
                    <span className="block text-[13px] font-semibold text-ink-900 truncate">{w.name}</span>
                    <span className="block text-[11px] text-ink-400 truncate">
                      {w.district} · {compactNumber(w.population)} people · {timeAgo(overview.data?.as_of, now)}
                    </span>
                  </span>
                  <span className="flex items-center gap-2 shrink-0">
                    <span className="text-[15px] font-extrabold tabular" style={{ color: LEVEL_COLOR[w.level] }}>
                      {Math.round(w.score)}
                    </span>
                    <LevelBadge level={w.level} size="sm" showDot={false} />
                  </span>
                </button>
              ))}
            </div>
          </Card>

          <LiveFeed />
        </div>
      </div>

      {/* ------------------------------------------------------------ advisories */}
      {critical.length > 0 && (
        <Card
          title={
            <span className="flex items-center gap-2 text-risk-red">
              <TriangleAlert size={16} />
              {critical.length} ward{critical.length > 1 ? "s" : ""} at warning level
            </span>
          }
          subtitle="These are the areas where the control room has been triggered automatically."
        >
          <div className="grid grid-auto-fill gap-3">
            {critical.map((w) => (
              <Link
                key={w.code}
                to={`/ward/${w.code}`}
                className="panel-tight p-3.5 hover:shadow-lg transition-shadow block"
                style={{ borderColor: LEVEL_COLOR[w.level] }}
              >
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <p className="text-[13px] font-bold truncate">{w.name}</p>
                  <LevelBadge level={w.level} size="sm" />
                </div>
                <p className="text-[11px] text-ink-600 leading-snug">{t(`advice.${w.level}`)}</p>
                <p className="text-[10px] text-ink-400 mt-2 tabular">
                  score {Math.round(w.score)} · {compactNumber(w.population_at_risk)} exposed ·{" "}
                  {Math.round(w.probability_24h * 100)}% in 24 h
                </p>
              </Link>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function Metric({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: string }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className="stat-value mt-1.5" style={tone ? { color: tone } : undefined}>
        {value}
      </p>
      {hint && <p className="text-[10px] text-ink-400 mt-1">{hint}</p>}
    </div>
  );
}

/**
 * Rolling operational feed. Only the anonymised event stream reaches this
 * component — reporter identities are never sent on the public channel.
 */
function LiveFeed() {
  const { events, status } = useLive();
  const now = useNow(10_000);
  const labels: Record<string, string> = {
    "risk:update": "risk recomputed",
    "alert:new": "warning issued",
    "report:new": "hazard reported",
    "report:corroborated": "report corroborated",
    "report:verdict": "report triaged",
    "shelter:update": "shelter occupancy",
    "road:update": "road status",
    "resource:update": "resource moved",
    replay: "backlog",
    pong: "",
  };

  const visible = events.filter((e) => e.event !== "risk:update").slice(0, 9);

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          Live activity
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: status === "open" ? "#22c55e" : "#eab308" }}
          />
        </span>
      }
      subtitle={status === "open" ? "Streaming over WebSocket" : "Reconnecting…"}
      bodyClass="p-0"
    >
      {visible.length === 0 ? (
        <EmptyState title="Nothing has changed yet" hint="This fills in as ward risk, reports and warnings move." />
      ) : (
        <ul className="max-h-[280px] overflow-y-auto">
          {visible.map((e, i) => {
            const data = e.data as Record<string, unknown>;
            const ward = (data?.ward_name || data?.ward || data?.name || "") as string;
            const detail = (data?.title || data?.status || data?.level || "") as string;
            return (
              <li key={`${e.at}-${i}`} className="px-4 py-2.5 border-b border-[var(--line)] last:border-0 flex gap-2.5">
                <span className="w-1 rounded-full shrink-0" style={{ background: LEVEL_COLOR[(data?.level as Level) ?? "blue"] ?? "#0ea5e9" }} />
                <div className="min-w-0 flex-1">
                  <p className="text-[12px] font-semibold text-ink-900 truncate">
                    {labels[e.event] ?? e.event}
                    {ward ? ` · ${ward}` : ""}
                  </p>
                  {detail && <p className="text-[11px] text-ink-400 truncate">{detail}</p>}
                </div>
                <span className="text-[10px] text-ink-400 tabular shrink-0">{timeAgo(e.at, now)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
