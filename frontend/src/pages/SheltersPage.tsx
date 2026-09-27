import { Accessibility, Droplet, Hospital, LifeBuoy, Phone, Search, Users, Zap } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { Shelter } from "../api/types";
import { Card, EmptyState, ErrorState, Loading, formatNumber, useDebounced } from "../components/ui";
import { MapMarker, RiskMap } from "../components/RiskMap";
import { PageHeader } from "../components/Layout";
import { useAsync, useGeolocate } from "../hooks";

export default function SheltersPage() {
  const { coords } = useGeolocate();
  const [query, setQuery] = useState("");
  const [onlySpace, setOnlySpace] = useState(true);
  const search = useDebounced(query, 250);

  const wardsQ = useAsync(() => api.overview(), []);
  const sheltersQ = useAsync(
    () =>
      api.shelters({
        lat: coords?.lat,
        lng: coords?.lng,
        only_space: onlySpace ? "true" : undefined,
      }),
    [coords?.lat, coords?.lng, onlySpace],
  );

  const shelters = sheltersQ.data?.shelters ?? [];
  const filtered = useMemo(
    () =>
      shelters.filter(
        (s) =>
          !search ||
          s.name.toLowerCase().includes(search.toLowerCase()) ||
          (s.ward_name ?? "").toLowerCase().includes(search.toLowerCase()),
      ),
    [shelters, search],
  );

  const markers: MapMarker[] = filtered.map((s) => ({
    id: s.code,
    lat: s.latitude,
    lng: s.longitude,
    kind: "shelter",
    label: s.name,
    meta: `${s.free_places} of ${s.capacity} free${s.has_medical ? " · medical" : ""}`,
    color: s.free_places > 0 ? "#16a34a" : "#dc2626",
  }));

  const totalFree = filtered.reduce((sum, s) => sum + s.free_places, 0);

  return (
    <div className="grid gap-5">
      <PageHeader
        eyebrow="Evacuation support"
        title="Shelters and assembly points"
        sub="Free space is reported by the field team and updates live — an address list is useless if the hall is already full. Capacity figures are planning numbers, not guarantees; call ahead where you can."
        actions={
          <div className="pill">
            <Users size={13} /> {formatNumber(totalFree)} places free across {filtered.length} shelters
          </div>
        }
      />

      {sheltersQ.error && <ErrorState error={sheltersQ.error} onRetry={sheltersQ.reload} />}

      <div className="grid lg:grid-cols-[1fr_1.25fr] gap-5 items-start">
        <Card bodyClass="p-0" title="Nearest with space" actions={
          <button className={`btn btn-sm ${onlySpace ? "btn-primary" : "btn-ghost"}`} onClick={() => setOnlySpace((v) => !v)}>
            {onlySpace ? "Showing open only" : "Showing all"}
          </button>
        }>
          <div className="p-3 border-b border-[var(--line)]">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
              <input
                className="input !pl-9 !py-2 text-sm"
                placeholder="Search shelter or ward…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
          </div>
          {sheltersQ.loading && !shelters.length ? <Loading label="Loading shelters…" /> : null}
          {!sheltersQ.loading && filtered.length === 0 && (
            <EmptyState title="No shelter matches" hint="Try turning off the open-only filter." icon={<LifeBuoy size={18} />} />
          )}
          <ul className="max-h-[560px] overflow-y-auto divide-y divide-[var(--line)]">
            {filtered.map((s) => (
              <ShelterRow key={s.code} shelter={s} hasCoords={!!coords} />
            ))}
          </ul>
        </Card>

        <Card bodyClass="p-0" title="Shelter map" subtitle="Green has space, red is full or overflowing.">
          <div className="h-[560px]">
            {wardsQ.loading ? (
              <Loading label="Preparing basemap…" />
            ) : (
              <RiskMap wards={wardsQ.data?.wards ?? []} markers={markers} height="100%" showLegend={false} />
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function ShelterRow({ shelter: s, hasCoords }: { shelter: Shelter; hasCoords: boolean }) {
  const full = s.free_places <= 0;
  const pct = Math.min(100, s.occupancy_pct);
  return (
    <li className="px-4 py-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-bold text-ink-900 leading-snug">{s.name}</p>
          <p className="text-[11px] text-ink-400 mt-0.5">
            {s.ward_name ?? "unassigned ward"} · {s.kind.replace(/_/g, " ")}
            {hasCoords && s.distance_km !== null && ` · ${s.distance_km} km`}
          </p>
        </div>
        <span
          className="chip shrink-0"
          style={{ background: full ? "#fef2f2" : pct > 85 ? "#fff7ed" : "#f0fdf4", color: full ? "#dc2626" : pct > 85 ? "#f97316" : "#16a34a" }}
        >
          {full ? "no space" : `${s.free_places} free`}
        </span>
      </div>

      <div className="mt-2.5 h-1.5 rounded-full bg-ink-100 overflow-hidden">
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{ width: `${pct}%`, background: full ? "#dc2626" : pct > 85 ? "#f97316" : "#16a34a" }}
        />
      </div>
      <p className="text-[10px] text-ink-400 mt-1 tabular">
        {formatNumber(s.occupied)} of {formatNumber(s.capacity)} occupied · {s.staff} staff · water for{" "}
        {s.water_security_days} day{s.water_security_days === 1 ? "" : "s"}
      </p>

      <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
        {s.has_medical && (
          <span className="pill !text-[10px] !py-0.5">
            <Hospital size={10} /> medical
          </span>
        )}
        {s.wheelchair_accessible && (
          <span className="pill !text-[10px] !py-0.5">
            <Accessibility size={10} /> step-free
          </span>
        )}
        {s.has_generator && (
          <span className="pill !text-[10px] !py-0.5">
            <Zap size={10} /> power
          </span>
        )}
        {s.has_medical && s.water_security_days >= 3 && (
          <span className="pill !text-[10px] !py-0.5">
            <Droplet size={10} /> water secured
          </span>
        )}
        {s.manager_phone && (
          <a
            href={`tel:${s.manager_phone.replace(/[^\d+]/g, "")}`}
            className="pill !text-[10px] !py-0.5 !border-risk-blue/40 !text-risk-blue font-bold ml-auto"
          >
            <Phone size={10} /> {s.manager_phone}
          </a>
        )}
      </div>
    </li>
  );
}
