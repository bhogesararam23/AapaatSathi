import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { HazardReport, Level, WardRiskSummary } from "../api/types";
import { LEVEL_COLOR } from "./ui";

export interface MapMarker {
  id: string;
  lat: number;
  lng: number;
  kind: "report" | "shelter" | "resource";
  label: string;
  color?: string;
  level?: Level;
  meta?: string;
}

interface Props {
  wards: WardRiskSummary[];
  selectedCode?: string | null;
  onSelectWard?: (code: string) => void;
  markers?: MapMarker[];
  /** Two-letter district focus, used by the console filters. */
  focus?: [number, number, number, number] | null;
  center?: [number, number];
  zoom?: number;
  height?: string | number;
  className?: string;
  showLegend?: boolean;
  interactive?: boolean;
}

/**
 * OpenStreetMap raster tiles via MapLibre.
 *
 * No API key, no account, no billed tier — which matters twice over here: the
 * project must clone-and-run for a reviewer, and a real district deployment
 * cannot be hostage to a mapping vendor's pricing. Attribution is rendered by
 * MapLibre automatically and must stay visible.
 */
const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#eef2f8" } },
    { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.92 } },
  ],
};

function wardNode(ward: WardRiskSummary, selected: boolean): HTMLElement {
  const el = document.createElement("div");
  const high = ward.level === "red" || ward.level === "orange";
  el.className = `ward-marker${high ? " critical" : ""}`;
  el.style.width = "20px";
  el.style.height = "20px";
  el.style.position = "relative";

  if (high) {
    const ring = document.createElement("span");
    ring.className = "ring";
    ring.style.background = LEVEL_COLOR[ward.level];
    el.appendChild(ring);
  }

  const dot = document.createElement("span");
  dot.className = "dot";
  dot.style.background = LEVEL_COLOR[ward.level];
  dot.style.position = "absolute";
  dot.style.inset = "0";
  dot.style.boxShadow = selected
    ? `0 0 0 3px #fff, 0 0 0 6px ${LEVEL_COLOR[ward.level]}`
    : "0 2px 6px rgba(11,18,32,.35)";
  dot.style.transition = "box-shadow .18s ease";
  el.appendChild(dot);

  const tip = document.createElement("div");
  tip.textContent = `${ward.name} · ${Math.round(ward.score)}`;
  Object.assign(tip.style, {
    position: "absolute",
    left: "50%",
    bottom: "150%",
    transform: "translateX(-50%)",
    background: "#0b1220",
    color: "#fff",
    fontSize: "11px",
    fontWeight: "600",
    padding: "3px 7px",
    borderRadius: "6px",
    whiteSpace: "nowrap",
    opacity: "0",
    pointerEvents: "none",
    transition: "opacity .15s",
  } as CSSStyleDeclaration);
  el.appendChild(tip);
  el.addEventListener("mouseenter", () => (tip.style.opacity = "1"));
  el.addEventListener("mouseleave", () => (tip.style.opacity = "0"));
  return el;
}

export function RiskMap({
  wards,
  selectedCode,
  onSelectWard,
  markers = [],
  focus,
  center,
  zoom = 8.2,
  height = "100%",
  className = "",
  showLegend = true,
  interactive = true,
}: Props) {
  const holder = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);
  // Style load is asynchronous. Ward data often arrives first — especially when
  // the API is on localhost and the tiles are not — so readiness has to be
  // React state, not just a ref, or the marker effect runs once, bails out, and
  // never re-runs. That presented as a blank map with data in the sidebar.
  const [loaded, setLoaded] = useState(false);
  const wardMarkers = useRef(new Map<string, maplibregl.Marker>());
  const otherMarkers = useRef(new Map<string, maplibregl.Marker>());
  const selectRef = useRef(onSelectWard);
  selectRef.current = onSelectWard;

  const startCenter = useMemo<[number, number]>(
    () => center ?? fitCentre(wards),
    [center, wards],
  );

  useEffect(() => {
    if (!holder.current || map.current) return;
    const m = new maplibregl.Map({
      container: holder.current,
      style: STYLE,
      center: startCenter,
      zoom,
      minZoom: 6,
      maxZoom: 15,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: "metric" }), "bottom-left");
    if (!interactive) {
      m.dragPan.disable();
      m.scrollZoom.disable();
      m.doubleClickZoom.disable();
    }
    m.on("load", () => setLoaded(true));
    // Safety net for a style that never finishes loading — hotel Wi-Fi in
    // Dehradun, a blocked tile CDN. Ward risk comes from the local API, not the
    // tile server, so markers should still appear even if basemap tiles do not.
    const styleFallback = window.setTimeout(() => setLoaded(true), 2000);
    map.current = m;

    return () => {
      // No setState here: the map is being torn down, and updating state from a
      // cleanup on an unmounting tree invites a re-render loop in StrictMode.
      window.clearTimeout(styleFallback);
      wardMarkers.current.clear();
      otherMarkers.current.clear();
      m.remove();
      map.current = null;
    };
    // Deliberately mount-once: recreating the map on every data tick would
    // throw away the user's pan/zoom while they are reading it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- ward markers -------------------------------------------------------- //
  useEffect(() => {
    const m = map.current;
    if (!m || !loaded) return;

    const seen = new Set<string>();
    wards.forEach((ward) => {
      seen.add(ward.code);
      // MapLibre markers have no in-place element swap, and re-creating a
      // marker is cheap compared to re-rendering the map: drop and rebuild.
      wardMarkers.current.get(ward.code)?.remove();
      const el = wardNode(ward, ward.code === selectedCode);
      el.style.cursor = "pointer";
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        selectRef.current?.(ward.code);
      });
      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([ward.longitude, ward.latitude])
        .setPopup(
          new maplibregl.Popup({ offset: 16, closeButton: false }).setHTML(popupHtml(ward)),
        )
        .addTo(m);
      wardMarkers.current.set(ward.code, marker);
    });

    wardMarkers.current.forEach((marker, code) => {
      if (!seen.has(code)) {
        marker.remove();
        wardMarkers.current.delete(code);
      }
    });
  }, [wards, selectedCode, loaded]);

  // ---- reports / shelters -------------------------------------------------- //
  useEffect(() => {
    const m = map.current;
    if (!m || !loaded) return;
    const seen = new Set<string>();
    markers.forEach((mk) => {
      seen.add(mk.id);
      if (otherMarkers.current.has(mk.id)) return;
      const el = document.createElement("div");
      el.title = mk.label + (mk.meta ? ` — ${mk.meta}` : "");
      Object.assign(el.style, {
        width: "14px",
        height: "14px",
        borderRadius: "9999px",
        background: mk.color ?? "#0b1220",
        border: "2px solid #fff",
        boxShadow: "0 2px 6px rgba(11,18,32,.3)",
        cursor: "pointer",
      } as CSSStyleDeclaration);
      if (mk.kind === "report") {
        el.style.borderRadius = "3px";
        el.style.transform = "rotate(45deg)";
      }
      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([mk.lng, mk.lat])
        .setPopup(
          new maplibregl.Popup({ offset: 14, closeButton: false }).setHTML(
            `<div style="padding:8px 11px;font:600 12px/1.45 Inter,system-ui;color:#0b1220">${escapeHtml(
              mk.label,
            )}${mk.meta ? `<div style="font-weight:400;color:#5b6b86;margin-top:2px">${escapeHtml(mk.meta)}</div>` : ""}</div>`,
          ),
        )
        .addTo(m);
      otherMarkers.current.set(mk.id, marker);
    });
    otherMarkers.current.forEach((marker, id) => {
      if (!seen.has(id)) {
        marker.remove();
        otherMarkers.current.delete(id);
      }
    });
  }, [markers, loaded]);

  // ---- selection fly-to ---------------------------------------------------- //
  useEffect(() => {
    const m = map.current;
    if (!m || !loaded || !selectedCode) return;
    const ward = wards.find((w) => w.code === selectedCode);
    if (!ward) return;
    m.flyTo({
      center: [ward.longitude, ward.latitude],
      zoom: Math.max(m.getZoom(), 10.5),
      duration: 900,
      essential: true,
    });
  }, [selectedCode, wards, loaded]);

  useEffect(() => {
    const m = map.current;
    if (!m || !loaded || !focus) return;
    m.fitBounds(
      [
        [focus[0], focus[1]],
        [focus[2], focus[3]],
      ],
      { padding: 48, duration: 800 },
    );
  }, [focus, loaded]);

  return (
    <div className={`relative overflow-hidden ${className}`} style={{ height }}>
      <div ref={holder} className="absolute inset-0" />
      {showLegend && <Legend />}
    </div>
  );
}

function Legend() {
  const items: [Level, string][] = [
    ["green", "Safe"],
    ["blue", "Advisory"],
    ["yellow", "Alert"],
    ["orange", "Warning"],
    ["red", "Evacuate"],
  ];
  return (
    <div className="absolute left-3 bottom-3 z-10 rounded-xl bg-white/95 backdrop-blur px-3 py-2.5 shadow-lg border border-[var(--line)] pointer-events-none">
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-ink-400 mb-1.5">
        Ward susceptibility
      </p>
      <div className="flex items-center gap-2.5">
        {items.map(([level, label]) => (
          <div key={level} className="flex items-center gap-1">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: LEVEL_COLOR[level], boxShadow: "0 0 0 1.5px #fff" }}
            />
            <span className="text-[10px] font-semibold text-ink-700">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function popupHtml(ward: WardRiskSummary): string {
  const top = [...ward.factors].sort((a, b) => b.contribution - a.contribution)[0];
  return `
  <div style="min-width:210px;padding:11px 13px;font-family:Inter,system-ui;color:#0b1220">
    <div style="font-size:13px;font-weight:700;line-height:1.3">${escapeHtml(ward.name)}</div>
    <div style="font-size:11px;color:#5b6b86;margin-bottom:7px">${escapeHtml(ward.district)} · ${ward.code}</div>
    <div style="display:flex;align-items:baseline;gap:6px">
      <span style="font-size:24px;font-weight:800;color:${LEVEL_COLOR[ward.level]};line-height:1">${Math.round(ward.score)}</span>
      <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:${LEVEL_COLOR[ward.level]}">${ward.level}</span>
    </div>
    <div style="font-size:11px;color:#27334a;margin-top:6px;line-height:1.5">
      ${ward.population.toLocaleString("en-IN")} people · ${top ? `top driver: ${escapeHtml(top.label.toLowerCase())}` : ""}
    </div>
    <div style="font-size:10px;color:#8ea0bd;margin-top:5px">Confidence ${Math.round(ward.confidence * 100)}% · click for the full briefing</div>
  </div>`;
}

function escapeHtml(text: string): string {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fitCentre(wards: WardRiskSummary[]): [number, number] {
  if (!wards.length) return [78.9, 30.15];
  const lat = wards.reduce((s, w) => s + w.latitude, 0) / wards.length;
  const lng = wards.reduce((s, w) => s + w.longitude, 0) / wards.length;
  return [+lng.toFixed(4), +lat.toFixed(4)];
}

export function reportsToMarkers(reports: HazardReport[]): MapMarker[] {
  return reports
    .filter((r) => r.status !== "dismissed" && r.status !== "resolved")
    .map((r) => ({
      id: r.code,
      lat: r.latitude,
      lng: r.longitude,
      kind: "report" as const,
      label: r.title || r.hazard_type.replace("_", " "),
      color: r.status === "confirmed" ? "#dc2626" : r.status === "under_review" ? "#f97316" : "#0b1220",
      meta: `${r.hazard_type.replace("_", " ")} · ${r.corroborated_by} corroborations · confidence ${Math.round(
        r.confidence * 100,
      )}%`,
    }));
}
