/**
 * API types. Hand-written to mirror `backend/app/schemas.py` and the assembly
 * payloads rather than generated, so the shapes stay readable and every field
 * the UI renders is intentional. Where the backend sends extra keys we simply
 * ignore them; where it sends `null` we model it explicitly.
 */

export type Level = "green" | "blue" | "yellow" | "orange" | "red";
export type Lang = "en" | "hi" | "gar";
export type Role = "citizen" | "field_responder" | "district_admin" | "system_admin";

export const LEVEL_ORDER: Level[] = ["green", "blue", "yellow", "orange", "red"];

export interface Factor {
  key: string;
  label: string;
  unit: string;
  observed: number;
  normalised: number;
  weight: number;
  contribution: number;
  rationale: string;
}

export interface District {
  id: number;
  code: string;
  name: string;
  name_hi: string;
  state: string;
  headquarters: string;
  latitude: number;
  longitude: number;
  area_km2: number;
  population: number;
  control_room: string;
}

export interface Ward {
  id: number;
  code: string;
  name: string;
  name_hi: string;
  district_id: number;
  latitude: number;
  longitude: number;
  polygon: [number, number][] | number[][];
  elevation_m: number;
  slope_deg: number;
  lithology: string;
  fault_distance_km: number;
  river_distance_km: number;
  ndvi: number;
  historical_events: number;
  population: number;
  households: number;
  children: number;
  elderly: number;
  disabled: number;
  registered_phones: number;
  schools: number;
  health_centres: number;
  connectivity: string;
  notes: string;
}

export interface WardRiskSummary {
  ward_id: number;
  code: string;
  name: string;
  name_hi: string;
  district: string;
  district_id: number;
  latitude: number;
  longitude: number;
  population: number;
  registered_phones: number;
  connectivity: string;
  slope_deg: number;
  lithology: string;
  historical_events: number;
  score: number;
  level: Level;
  confidence: number;
  crowd_uplift: number;
  probability_24h: number;
  population_at_risk: number;
  model_version: string;
  factors: Factor[];
  inputs: {
    rain_1h_mm: number;
    rain_24h_mm: number;
    rain_72h_mm: number;
    forecast_6h_mm: number;
    soil_moisture: number;
    river_level_m: number;
    gauge_online: boolean;
    telemetry_age_minutes: number | null;
    open_reports: number;
    confirmed_reports: number;
  };
}

export interface NearbyShelter {
  code: string;
  name: string;
  kind: string;
  distance_km: number;
  capacity: number;
  occupied: number;
  free_places: number;
  has_medical: boolean;
  wheelchair_accessible: boolean;
  status: string;
  latitude: number;
  longitude: number;
  manager_phone: string;
  bearing_deg: number;
}

export interface RoadState {
  code: string;
  name: string;
  status: "open" | "caution" | "partial" | "closed";
  is_lifeline: boolean;
  length_km: number;
  note: string;
  clearance_eta_hours: number | null;
  updated_at: string | null;
}

export interface WardDetail extends WardRiskSummary {
  polygon: number[][];
  notes: string;
  elevation_m: number;
  aspect_deg: number;
  road_distance_km: number;
  households: number;
  children: number;
  elderly: number;
  disabled: number;
  schools: number;
  health_centres: number;
  fault_distance_km: number;
  river_distance_km: number;
  ndvi: number;
  nearest_shelters: NearbyShelter[];
  recent_reports: HazardReport[];
  roads: RoadState[];
  rainfall_series: { at: string; rain_mm: number; forecast: boolean }[];
}

export interface Overview {
  as_of: string;
  wards: WardRiskSummary[];
  levels: Record<Level, number>;
  population_exposed: number;
  highest: WardRiskSummary | null;
  mean_confidence: number;
}

export interface ModelInfo {
  version: string;
  weights: Record<string, number>;
  thresholds: Record<string, number>;
  weights_sum: number;
  crowd_uplift_cap: number;
  active_config: string;
  factor_docs: { key: string; name: string; source: string; kind: string; weight: number }[];
  disclaimer: string;
}

export interface HazardReport {
  id: number;
  code: string;
  ward_id: number | null;
  ward_name?: string;
  district_name?: string;
  hazard_type: string;
  title: string;
  description: string;
  latitude: number;
  longitude: number;
  accuracy_m: number;
  self_severity: number;
  status: "new" | "under_review" | "confirmed" | "dismissed" | "resolved";
  source: string;
  confidence: number;
  corroborated_by: number;
  responders_dispatched: number;
  photo_url: string | null;
  reporter_alias?: string | null;
  created_at: string;
  verified_at: string | null;
  resolution_note?: string;
}

export interface ReportResponse {
  merged: boolean;
  report: HazardReport;
  confidence: {
    value: number;
    components: Record<string, number>;
    weights: Record<string, number>;
  };
  message: string;
}

export interface Alert {
  id: number;
  code: string;
  ward_id: number | null;
  ward_name?: string | null;
  district_id: number | null;
  hazard_type: string;
  level: Level;
  title: string;
  message: string;
  localized: Record<string, { subject: string; sms: string; ivr: string; advice: string; level_name: string }>;
  score: number;
  advice: string;
  auto_issued: boolean;
  status: string;
  channels: string[];
  reach_target: number;
  delivered: number;
  acknowledged: number;
  issued_at: string;
  expires_at: string | null;
  minutes_left?: number | null;
}

export interface Shelter {
  id: number;
  code: string;
  name: string;
  ward_id: number | null;
  ward_name: string | null;
  latitude: number;
  longitude: number;
  kind: string;
  capacity: number;
  occupied: number;
  staff: number;
  has_medical: boolean;
  has_generator: boolean;
  wheelchair_accessible: boolean;
  water_security_days: number;
  manager_name: string;
  manager_phone: string;
  status: string;
  free_places: number;
  occupancy_pct: number;
  distance_km: number | null;
  last_updated_at: string;
}

export interface Road {
  id: number;
  code: string;
  name: string;
  district_id: number | null;
  district_name: string | null;
  from_ward_id: number | null;
  to_ward_id: number | null;
  from_ward_name: string | null;
  to_ward_name: string | null;
  polyline: number[][];
  length_km: number;
  status: "open" | "caution" | "partial" | "closed";
  is_lifeline: boolean;
  note: string;
  clearance_eta_hours: number | null;
  updated_at: string;
}

export interface ResourceUnit {
  id: number;
  code: string;
  name: string;
  kind: string;
  ward_id: number | null;
  ward_name: string | null;
  latitude: number;
  longitude: number;
  personnel: number;
  status: string;
  eta_hours: number | null;
  note: string;
  updated_at: string;
}

export interface Analytics {
  wards: number;
  districts: number;
  population_covered: number;
  phones_reachable: number;
  alerts_24h: number;
  reports_24h: number;
  reports_verified_24h: number;
  open_reports: number;
  shelters: number;
  shelter_capacity: number;
  shelter_occupied: number;
  roads_closed: number;
  roads_total: number;
  levels: Record<Level, number>;
  population_exposed: number;
  mean_confidence: number;
  median_lead_minutes: number | null;
  telemetry_source: string;
  generated_at: string;
}

export interface DeliveryStats {
  provider: string;
  simulated: boolean;
  by_status: Record<string, number>;
  by_channel: Record<string, number>;
  by_lang: Record<string, number>;
  total: number;
  reach_target: number;
  note: string;
}

export interface AuditEntry {
  id: number;
  actor_label: string;
  action: string;
  entity: string;
  entity_id: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface User {
  id: number;
  full_name: string;
  email: string | null;
  phone: string | null;
  role: Role;
  preferred_lang: Lang;
  is_active: boolean;
  is_verified: boolean;
  trust_score: number;
  district_id: number | null;
  ward_id: number | null;
  created_at: string;
}

export interface Session extends User {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export interface Meta {
  app: { name: string; title: string; title_hi: string; tagline: string; version: string };
  levels: Level[];
  level_names: Record<Level, Record<Lang, string>>;
  hazards: string[];
  hazard_names: Record<string, Record<Lang, string>>;
  channels: string[];
  report_statuses: string[];
  road_statuses: string[];
  languages: Lang[];
  catalog: Record<string, string>;
  emergency_numbers: Record<string, string>;
  model_version: string;
  telemetry: string;
  ward_count: number;
}

export interface LiveEvent {
  event: string;
  data: unknown;
  at: string;
}

export interface NotificationRow {
  id: number;
  alert_id: number | null;
  /** Masked server-side: a breach of this table must not leak a resident directory. */
  phone: string | null;
  channel: string;
  lang: string;
  body: string;
  status: "sent" | "simulated" | "queued" | "failed";
  provider: string;
  provider_ref: string | null;
  error: string | null;
  attempts: number;
  created_at: string;
  sent_at: string | null;
}

export interface CoverageRow {
  district: string;
  wards: number;
  population: number;
  phones: number;
  exposed: number;
  mean_score: number;
  worst_level: Level;
}
