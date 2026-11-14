export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as Record<string, unknown>).detail)
        : `Erreur HTTP ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

const get = <T>(url: string) => request<T>(url);
const post = <T>(url: string, body?: unknown) =>
  request<T>(url, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T>(url: string, body: unknown) =>
  request<T>(url, { method: "PATCH", body: JSON.stringify(body) });
const del = <T>(url: string) => request<T>(url, { method: "DELETE" });

export const api = {
  network: () =>
    get<{
      interfaces: Array<Record<string, unknown>>;
      devices: unknown[];
      last_scan: { report?: import("../types").ScanReport } | null;
      online_vendor_lookup: boolean;
    }>("/api/network"),
  scan: (online?: boolean) =>
    post<import("../types").ScanReport>(
      `/api/network/scan${online === undefined ? "" : `?online=${online}`}`,
    ),
  robot: () =>
    get<{
      snapshot: import("../types").RobotSnapshot;
      commands: import("../types").CommandMeta;
      has_credentials: boolean;
      ip_hint: string | null;
    }>("/api/robot"),
  saveCredentials: (blid: string, password: string, host: string) =>
    post<{ ok: boolean; snapshot: import("../types").RobotSnapshot }>(
      "/api/robot/credentials",
      { blid, password, host },
    ),
  clearCredentials: () => del<{ ok: boolean }>("/api/robot/credentials"),
  connect: () => post<{ ok: boolean }>("/api/robot/connect"),
  disconnect: () => post<{ ok: boolean }>("/api/robot/disconnect"),
  command: (command: string, confirm = false) =>
    post<{ ok: boolean; command: string }>("/api/robot/command", { command, confirm }),
  missions: () => get<{ missions: import("../types").Mission[] }>("/api/missions"),
  events: () => get<{ events: import("../types").AppEvent[] }>("/api/events"),
  telemetry: (minutes = 120) =>
    get<{ samples: import("../types").TelemetrySample[] }>(
      `/api/telemetry?minutes=${minutes}`,
    ),
  stats: () =>
    get<{ missions: number; seconds: number; sqft: number; avg_seconds: number }>(
      "/api/stats",
    ),
  settings: () => get<{ online_vendor_lookup: boolean }>("/api/settings"),
  saveSettings: (online_vendor_lookup: boolean) =>
    post<{ online_vendor_lookup: boolean }>("/api/settings", { online_vendor_lookup }),
  schedules: () =>
    get<{ schedules: import("../types").Schedule[]; next: Record<string, number> }>(
      "/api/schedules",
    ),
  createSchedule: (payload: {
    name: string;
    days: number[];
    at_time: string;
    command?: string;
    enabled?: boolean;
  }) =>
    post<{ schedule: import("../types").Schedule; next: Record<string, number> }>(
      "/api/schedules",
      payload,
    ),
  updateSchedule: (id: number, payload: Partial<import("../types").Schedule>) =>
    patch<{ schedule: import("../types").Schedule; next: Record<string, number> }>(
      `/api/schedules/${id}`,
      payload,
    ),
  deleteSchedule: (id: number) => del<{ ok: boolean }>(`/api/schedules/${id}`),
  runSchedule: (id: number) =>
    post<{ ok: boolean; schedule: import("../types").Schedule }>(
      `/api/schedules/${id}/run`,
      { confirm: true },
    ),
  cloudRetrieve: (email: string, password: string, host?: string) =>
    post<{
      ok: boolean;
      saved?: boolean;
      blid?: string;
      password?: string;
      robot_name?: string | null;
      robots_found?: number;
      snapshot?: import("../types").RobotSnapshot;
      error?: string;
      detail?: string;
    }>("/api/robot/cloud-retrieve", { email, password, host: host || undefined }),
};
