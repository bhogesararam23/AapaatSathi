import { Ban, CheckCircle2, Route, Timer, TriangleAlert } from "lucide-react";
import { api } from "../api/client";
import type { Road } from "../api/types";
import { Card, EmptyState, ErrorState, Loading, formatNumber, timeAgo } from "../components/ui";
import { MapMarker, RiskMap } from "../components/RiskMap";
import { PageHeader } from "../components/Layout";
import { useAsync, useNow } from "../hooks";

const ROAD_COLOR: Record<string, string> = {
  open: "#16a34a",
  caution: "#ca8a04",
  partial: "#f97316",
  closed: "#dc2626",
};

export default function RoadsPage() {
  const roadsQ = useAsync(() => api.roads(), [], { intervalMs: 90_000 });
  const wardsQ = useAsync(() => api.overview(), []);
  const now = useNow();

  const roads = roadsQ.data?.roads ?? [];
  const blocked = roads.filter((r) => r.status === "closed" || r.status === "partial");

  const markers: MapMarker[] = blocked.map((r) => {
    const mid = midpoint(r);
    return {
      id: r.code,
      lat: mid[1],
      lng: mid[0],
      kind: "resource",
      label: r.name,
      meta: `${r.status}${r.clearance_eta_hours ? ` · clears ~${r.clearance_eta_hours} h` : ""}`,
      color: ROAD_COLOR[r.status],
    };
  });

  return (
    <div className="grid gap-5">
      <PageHeader
        eyebrow="Access"
        title="Road status"
        sub="Which routes a relief column can actually use. A landslide warning that sends an ambulance down a closed road is worse than no warning, so this board is maintained by the field team and updates live."
        actions={
          <>
            <span className="pill">
              <Route size={13} /> {roads.length} monitored segments
            </span>
            {blocked.length > 0 && (
              <span className="chip" style={{ background: "#fef2f2", color: "#dc2626" }}>
                <Ban size={12} /> {blocked.length} impaired
              </span>
            )}
          </>
        }
      />

      {roadsQ.error && <ErrorState error={roadsQ.error} onRetry={roadsQ.reload} />}

      <div className="grid lg:grid-cols-[1.1fr_1fr] gap-5 items-start">
        <div className="grid gap-5">
          <Card title="Impaired and lifeline routes" bodyClass="p-0">
            {roadsQ.loading && !roads.length ? (
              <Loading label="Loading road network…" />
            ) : blocked.length === 0 ? (
              <EmptyState title="Every monitored segment is open" icon={<CheckCircle2 size={18} />} />
            ) : (
              <ul className="divide-y divide-[var(--line)]">
                {blocked.map((r) => (
                  <RoadRow key={r.code} road={r} now={now} />
                ))}
              </ul>
            )}
          </Card>

          <Card title="Open routes" bodyClass="p-0" subtitle={`${roads.length - blocked.length} segments moving`}>
            <ul className="divide-y divide-[var(--line)] max-h-[420px] overflow-y-auto">
              {roads
                .filter((r) => r.status === "open")
                .map((r) => (
                  <RoadRow key={r.code} road={r} now={now} />
                ))}
            </ul>
          </Card>
        </div>

        <Card bodyClass="p-0" title="Network map" subtitle="Markers sit at each impaired segment.">
          <div className="h-[460px]">
            {wardsQ.data ? (
              <RiskMap wards={wardsQ.data.wards} markers={markers} height="100%" showLegend={false} />
            ) : (
              <Loading label="Loading map…" />
            )}
          </div>
          <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
            {(["open", "caution", "partial", "closed"] as const).map((s) => (
              <div key={s}>
                <p className="eyebrow flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full" style={{ background: ROAD_COLOR[s] }} />
                  {s}
                </p>
                <p className="text-xl font-extrabold tabular mt-1">{roadsQ.data?.by_status?.[s] ?? 0}</p>
              </div>
            ))}
            <div className="col-span-2 text-[11px] text-ink-400 leading-relaxed pt-1">
              Lifelines blocked:{" "}
              <strong className={roadsQ.data?.lifelines_blocked ? "text-risk-red" : "text-risk-green"}>
                {roadsQ.data?.lifelines_blocked ?? 0}
              </strong>{" "}
              — a blocked lifeline is the number the control room escalates first, because it decides whether a
              stranded village can be reached at all.
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function RoadRow({ road: r, now }: { road: Road; now: number }) {
  const color = ROAD_COLOR[r.status];
  const impaired = r.status === "closed" || r.status === "partial";
  return (
    <li className="px-4 py-3 flex items-start gap-3">
      <span className="w-1 self-stretch rounded-full shrink-0" style={{ background: color }} />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-ink-900 truncate">{r.name}</p>
        <p className="text-[11px] text-ink-400 truncate">
          {r.from_ward_name ?? "?"} → {r.to_ward_name ?? "?"} · {formatNumber(r.length_km)} km · updated{" "}
          {timeAgo(r.updated_at, now)}
        </p>
        {r.note && <p className="text-[11px] text-ink-600 mt-1 leading-snug italic">“{r.note}”</p>}
      </div>
      <div className="text-right shrink-0">
        <span className="chip" style={{ background: `${color}18`, color }}>
          {r.status}
        </span>
        {impaired && r.is_lifeline && (
          <p className="text-[10px] font-bold text-risk-red mt-1.5 flex items-center gap-1 justify-end">
            <TriangleAlert size={10} /> lifeline
          </p>
        )}
        {r.clearance_eta_hours !== null && (
          <p className="text-[10px] text-ink-400 mt-1 flex items-center gap-1 justify-end">
            <Timer size={10} /> ~{r.clearance_eta_hours} h
          </p>
        )}
      </div>
    </li>
  );
}

function midpoint(r: Road): [number, number] {
  if (r.polyline?.length >= 2) {
    const a = r.polyline[0];
    const b = r.polyline[r.polyline.length - 1];
    return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  }
  return [78.9, 30.1];
}
