import type {
  Alert,
  Analytics,
  AuditEntry,
  CoverageRow,
  DeliveryStats,
  District,
  HazardReport,
  Meta,
  ModelInfo,
  NotificationRow,
  Overview,
  ReportResponse,
  ResourceUnit,
  Road,
  Session,
  Shelter,
  User,
  Ward,
  WardDetail,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) || "";
export const API_ROOT = `${BASE}/api/v1`;

const TOKEN_KEY = "aapaatsathi.token";
const REFRESH_KEY = "aapaatsathi.refresh";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string, r: string) => {
    localStorage.setItem(TOKEN_KEY, t);
    localStorage.setItem(REFRESH_KEY, r);
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
  refresh: () => localStorage.getItem(REFRESH_KEY),
};

export class ApiError extends Error {
  status: number;
  fields?: Record<string, string>;
  constructor(status: number, message: string, fields?: Record<string, string>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function parse(res: Response) {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Send as multipart/form-data (used for photo uploads). */
  form?: FormData;
  /** Skip the automatic bearer header (public endpoints). */
  anonymous?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}, retry = true): Promise<T> {
  const { body, form, anonymous, headers, ...rest } = options;
  const auth = anonymous ? null : tokenStore.get();

  const init: RequestInit = {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(auth ? { Authorization: `Bearer ${auth}` } : {}),
      ...(form ? {} : body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers as Record<string, string>),
    },
    body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
  };

  let res: Response;
  try {
    res = await fetch(`${API_ROOT}${path}`, init);
  } catch (err) {
    throw new ApiError(0, "Cannot reach the AapaatSathi API. Is the backend running on port 8000?", {
      network: String(err),
    });
  }

  // One transparent refresh attempt, then give up rather than loop.
  if (res.status === 401 && retry && !anonymous && tokenStore.refresh()) {
    const ok = await tryRefresh();
    if (ok) return request<T>(path, options, false);
  }
  if (res.status === 401 && !retry) onUnauthorized?.();

  const payload = await parse(res);
  if (!res.ok) {
    const detail =
      (payload as { detail?: string } | null)?.detail ||
      (payload as { message?: string } | null)?.message ||
      `Request failed (${res.status})`;
    throw new ApiError(res.status, detail, (payload as { fields?: Record<string, string> })?.fields);
  }
  return payload as T;
}

let refreshing: Promise<boolean> | null = null;
async function tryRefresh(): Promise<boolean> {
  refreshing ??= (async () => {
    const rt = tokenStore.refresh();
    if (!rt) return false;
    try {
      const res = await fetch(`${API_ROOT}/auth/refresh?refresh_token=${encodeURIComponent(rt)}`, {
        method: "POST",
      });
      if (!res.ok) return false;
      const data = (await res.json()) as Session & { user: unknown };
      tokenStore.set(data.access_token, data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

const q = (params: Record<string, string | number | boolean | undefined | null>) => {
  const usp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") usp.set(k, String(v));
  });
  const s = usp.toString();
  return s ? `?${s}` : "";
};

export const api = {
  // ------------------------------------------------------------- public
  meta: () => request<Meta>("/meta"),
  health: () => request<Record<string, unknown>>("/health", { anonymous: true }),
  districts: () => request<District[]>("/districts"),
  wards: (district?: string) => request<Ward[]>(`/wards${q({ district })}`),
  overview: (district?: string) => request<Overview>(`/risk/overview${q({ district })}`),
  model: () => request<ModelInfo>("/risk/model"),
  leaderboard: (limit = 10) => request<{ wards: Overview["wards"] }>(`/risk/leaderboard${q({ limit })}`),
  ward: (code: string) => request<WardDetail>(`/wards/${code}`),
  wardSeries: (code: string, hours = 48) =>
    request<Record<string, unknown>>(`/geo/wards/${code}/series${q({ hours })}`),
  history: (code: string) => request<{ points: Record<string, unknown>[] }>(`/risk/history/${code}`),
  liveAlerts: () => request<{ count: number; alerts: Alert[] }>("/alerts/live"),
  alerts: (params: Record<string, string | number | boolean | undefined> = {}) =>
    request<{ count: number; alerts: Alert[] }>(`/alerts${q(params)}`),
  reports: (params: Record<string, string | number | boolean | undefined> = {}) =>
    request<{ count: number; reports: HazardReport[] }>(`/reports${q(params)}`),
  reportStats: () => request<Record<string, unknown>>("/reports/stats"),
  shelters: (params: Record<string, string | number | boolean | undefined> = {}) =>
    request<{ count: number; total_capacity: number; total_free: number; shelters: Shelter[] }>(
      `/shelters${q(params)}`,
    ),
  roads: (params: Record<string, string | number | boolean | undefined> = {}) =>
    request<{ count: number; by_status: Record<string, number>; lifelines_blocked: number; roads: Road[] }>(
      `/roads${q(params)}`,
    ),
  resources: () => request<ResourceUnit[]>("/resources"),
  analytics: () => request<Analytics>("/analytics/summary"),
  timeseries: (hours = 24) =>
    request<{ points: { hour: string; mean_score: number; max_score: number; wards_high_alert: number; population_exposed: number }[] }>(
      `/analytics/timeseries${q({ hours })}`,
    ),
  coverage: () => request<{ districts: CoverageRow[]; users_reachable: number }>("/analytics/coverage"),

  // --------------------------------------------------------------- auth
  login: (identifier: string, password: string) =>
    request<Session>("/auth/login", { method: "POST", body: { identifier, password }, anonymous: true }),
  register: (payload: Record<string, unknown>) =>
    request<Session>("/auth/register", { method: "POST", body: payload, anonymous: true }),
  me: () => request<User>("/auth/me"),
  subscriptions: () => request<{ ward_code: string; ward_name: string; channel: string; lang: string; min_level: string }[]>(`/me/subscriptions`),
  subscribe: (wardCode: string, params: Record<string, string>) =>
    request<Record<string, unknown>>(`/me/subscriptions/${wardCode}${q(params)}`, { method: "POST" }),
  unsubscribe: (wardCode: string) =>
    request<Record<string, unknown>>(`/me/subscriptions/${wardCode}`, { method: "DELETE" }),

  // ----------------------------------------------------------- mutating
  fileReport: (form: FormData) =>
    request<ReportResponse>("/reports", { method: "POST", form }),
  corroborate: (code: string) =>
    request<{ code: string; corroborated_by: number; confidence: number }>(`/reports/${code}/corroborate`, {
      method: "POST",
    }),
  verdict: (code: string, status: string, note = "") =>
    request<{ report: HazardReport }>(`/reports/${code}/verdict`, { method: "PATCH", body: { status, note } }),
  dispatchReport: (code: string) =>
    request<Record<string, unknown>>(`/reports/${code}/dispatch`, { method: "POST" }),

  createAlert: (payload: Record<string, unknown>) =>
    request<Alert>("/alerts", { method: "POST", body: payload }),
  previewAlert: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/alerts/preview", { method: "POST", body: payload }),
  broadcastAlert: (code: string) =>
    request<{ reach: Record<string, number> }>(`/alerts/${code}/broadcast`, { method: "POST" }),
  ackAlert: (code: string) =>
    request<Record<string, unknown>>(`/alerts/${code}/acknowledge`, { method: "POST" }),
  setAlertStatus: (code: string, status: string) =>
    request<Alert>(`/alerts/${code}/status`, { method: "PATCH", body: { status } }),

  updateShelter: (code: string, payload: Record<string, unknown>) =>
    request<Shelter>(`/shelters/${code}`, { method: "PATCH", body: payload }),
  updateRoad: (code: string, payload: Record<string, unknown>) =>
    request<{ code: string; status: string }>(`/roads/${code}/status`, { method: "PATCH", body: payload }),
  updateResource: (code: string, params: Record<string, string | number>) =>
    request<Record<string, unknown>>(`/resources/${code}/status${q(params)}`, { method: "PATCH" }),

  sweep: (broadcast = true) =>
    request<Record<string, unknown>>(`/risk/sweep${q({ broadcast })}`, { method: "POST" }),
  scenario: (payload: Record<string, unknown>) =>
    request<{ ward: Record<string, unknown>; escalation: Record<string, unknown> | null }>(
      "/risk/scenario",
      { method: "POST", body: payload },
    ),
  deliveryStats: () => request<DeliveryStats>("/notifications/stats"),
  notifications: (params: Record<string, string | number> = {}) =>
    request<{ count: number; notifications: NotificationRow[] }>(`/notifications${q(params)}`),
  audit: (params: Record<string, string | number> = {}) =>
    request<{ entries: AuditEntry[] }>(`/analytics/audit${q(params)}`),
  testNotify: (toPhone?: string) =>
    request<Record<string, unknown>>(`/notifications/test${q({ to_phone: toPhone })}`, { method: "POST" }),
};

export { q as queryString };
