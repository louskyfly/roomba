export type RobotSnapshot = {
  configured: boolean;
  connected: boolean;
  status: string;
  link: {
    host?: string;
    connected_at?: number | null;
    messages?: number;
    last_error?: string | null;
  } | null;
  identity: {
    name?: string | null;
    sku?: string | null;
    software?: string | null;
    battery_type?: string | null;
    country?: string | null;
  };
  battery: number | null;
  bin?: { present?: boolean; full?: boolean } | null;
  dock?: { known?: boolean } | null;
  mission?: {
    cycle?: string;
    phase?: string;
    error?: number;
    mssnM?: number;
    sqft?: number;
    nMssn?: number;
    initiator?: string;
    notReady?: number;
  } | null;
  mission_label?: string | null;
  status_label?: string;
  schedule?: { cycle?: string[]; h?: number[]; m?: number[] } | null;
  signal?: { rssi?: number; snr?: number } | null;
  pose?: { theta?: number; point?: { x?: number; y?: number } } | null;
  map?: {
    maps: Array<{
      id: string;
      version?: string | null;
      rooms: Array<{ id?: string; name?: string; type?: string }>;
    }>;
  } | null;
  last_command?: {
    command?: string;
    time?: number;
    initiator?: string;
  } | null;
  counters?: {
    bbrun?: {
      hr?: number;
      min?: number;
      sqft?: number;
      nStuck?: number;
      nPicks?: number;
      nPanics?: number;
    } | null;
    bbchg3?: {
      avgMin?: number;
      hOnDock?: number;
      nAvail?: number;
      estCap?: number;
    } | null;
    bbmssn?: {
      nMssn?: number;
      nMssnOk?: number;
      nMssnC?: number;
      nMssnF?: number;
      aMssnM?: number;
    } | null;
  };
  updated_at?: number | null;
  ip_hint?: string | null;
};

export type ServiceEntry = {
  port: number;
  service: string;
  state: string;
};

export type MdnsService = {
  service: string;
  instance: string;
  port?: number | null;
  txt?: Record<string, string>;
};

export type Device = {
  ip: string;
  mac?: string | null;
  vendor?: string | null;
  hostname?: string | null;
  kind: string;
  kind_label: string;
  label: string;
  confidence?: string;
  evidence: string[];
  ports: ServiceEntry[];
  tls?: {
    port?: number;
    tls?: string;
    cipher?: string;
    common_name?: string;
    organization?: string;
    issuer_cn?: string;
    not_after?: string;
    error?: string;
  } | null;
  mdns?: { names: string[]; services: MdnsService[] } | null;
  ssdp?: {
    names?: string[];
    device?: Record<string, string>;
    entries?: Array<{ st?: string; server?: string; location?: string }>;
  } | null;
  locally_administered?: boolean;
  self?: boolean;
};

export type ScanReport = {
  started_at: number;
  finished_at: number;
  duration_s: number;
  interface: {
    name: string;
    ip: string;
    prefix: number;
    mac?: string | null;
    gateway?: string | null;
    subnet: string;
    broadcast: string;
  };
  subnet: string;
  hosts_found: number;
  robot: Device | null;
  devices: Device[];
};

export type Mission = {
  id: number;
  number?: number | null;
  started_at: number;
  ended_at?: number | null;
  phase?: string | null;
  cycle?: string | null;
  error?: number;
  duration_s?: number | null;
  area_sqft?: number | null;
  battery_start?: number | null;
  battery_end?: number | null;
};

export type AppEvent = {
  id: number;
  ts: number;
  level: "info" | "warning" | "error" | string;
  kind: string;
  message: string;
  data?: string | null;
};

export type TelemetrySample = {
  id: number;
  ts: number;
  battery?: number | null;
  phase?: string | null;
  cycle?: string | null;
  error?: number | null;
  x?: number | null;
  y?: number | null;
  theta?: number | null;
  mission_id?: number | null;
};

export type CommandMeta = Record<
  string,
  { label: string; risky: boolean }
>;

export type Schedule = {
  id: number;
  name: string;
  enabled: boolean;
  days: number[];
  at_time: string;
  command: string;
  created_at: number;
  last_run_at?: number | null;
  last_result?: string | null;
};
