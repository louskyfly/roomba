import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./lib/api";
import type {
  AppEvent,
  CommandMeta,
  Device,
  Mission,
  RobotSnapshot,
  ScanReport,
  Schedule,
  TelemetrySample,
} from "./types";
import { statusText } from "./lib/format";
import { Toasts, type Toast, Modal, Button } from "./components/ui";
import { Dashboard } from "./pages/Dashboard";
import { Network } from "./pages/Network";
import { Control } from "./pages/Control";
import { Planning } from "./pages/Planning";
import { MapPage } from "./pages/MapPage";
import { Settings } from "./pages/Settings";

export type Tab = "dashboard" | "network" | "control" | "planning" | "map" | "settings";

const TABS: Array<{ id: Tab; label: string; icon: string; title: string; sub: string }> = [
  { id: "dashboard", label: "Tableau de bord", icon: "◉", title: "Tableau de bord", sub: "Vue d'ensemble du robot" },
  { id: "network", label: "Réseau", icon: "⌁", title: "Analyse réseau", sub: "Découverte locale, phase 1" },
  { id: "control", label: "Contrôle", icon: "▶", title: "Contrôle", sub: "Commandes locales authentifiées" },
  { id: "planning", label: "Planning", icon: "◷", title: "Planning", sub: "Nettoyages programmés" },
  { id: "map", label: "Carte", icon: "◇", title: "Cartographie", sub: "Trajectoires et zones" },
  { id: "settings", label: "Réglages", icon: "⚙", title: "Réglages", sub: "Appairage et sécurité" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>(() => {
    const h = window.location.hash.replace("#", "") as Tab;
    return TABS.some((t) => t.id === h) ? h : "dashboard";
  });
  const [snapshot, setSnapshot] = useState<RobotSnapshot | null>(null);
  const [commands, setCommands] = useState<CommandMeta>({});
  const [scan, setScan] = useState<ScanReport | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetrySample[]>([]);
  const [stats, setStats] = useState({ missions: 0, seconds: 0, sqft: 0, avg_seconds: 0 });
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [nextRuns, setNextRuns] = useState<Record<string, number>>({});
  const [confirmSchedule, setConfirmSchedule] = useState<Schedule | null>(null);
  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState<{ percent: number; message: string } | null>(null);
  const [onlineVendor, setOnlineVendor] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [confirmCmd, setConfirmCmd] = useState<string | null>(null);
  const toastId = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);

  const pushToast = useCallback((message: string, tone: Toast["tone"] = "info") => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, message, tone }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5200);
  }, []);

  const refreshHistory = useCallback(async () => {
    const [m, e, t, s] = await Promise.allSettled([
      api.missions(),
      api.events(),
      api.telemetry(180),
      api.stats(),
    ]);
    if (m.status === "fulfilled") setMissions(m.value.missions);
    if (e.status === "fulfilled") setEvents(e.value.events);
    if (t.status === "fulfilled") setTelemetry(t.value.samples);
    if (s.status === "fulfilled") setStats(s.value);
  }, []);

  const refreshSchedules = useCallback(async () => {
    try {
      const r = await api.schedules();
      setSchedules(r.schedules);
      setNextRuns(r.next);
    } catch {
      /* backend indisponible */
    }
  }, []);

  const refreshRobot = useCallback(async () => {
    try {
      const r = await api.robot();
      setSnapshot(r.snapshot);
      setCommands(r.commands);
    } catch {
      /* le backend n'est peut-être pas encore prêt */
    }
  }, []);

  useEffect(() => {
    void refreshRobot();
    void refreshHistory();
    void refreshSchedules();
    api
      .network()
      .then((n) => {
        setOnlineVendor(n.online_vendor_lookup);
        if (n.last_scan?.report) {
          setScan(n.last_scan.report);
          setDevices(n.last_scan.report.devices);
        }
      })
      .catch(() => undefined);
  }, [refreshRobot, refreshHistory, refreshSchedules]);

  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    let timer: number | undefined;
    let closed = false;

    const connect = () => {
      const ws = new WebSocket(`${proto}://${window.location.host}/ws`);
      wsRef.current = ws;
      ws.onopen = () => {
        if (!closed) setProgress(null);
      };
      ws.onmessage = (ev) => {
        let msg: Record<string, unknown>;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (msg.type === "robot") {
          setSnapshot(msg.snapshot as RobotSnapshot);
        } else if (msg.type === "hello") {
          setSnapshot(msg.robot as RobotSnapshot);
          const sc = msg.scan as { report?: ScanReport } | null;
          if (sc?.report) {
            setScan(sc.report);
            setDevices(sc.report.devices);
          }
        } else if (msg.type === "schedules_changed") {
          void refreshSchedules();
        } else if (msg.type === "schedule_run") {
          void refreshSchedules();
          const result = msg.result as { ok?: boolean; reason?: string } | undefined;
          pushToast(
            result?.ok
              ? `Passage « ${msg.name} » lancé`
              : `Passage « ${msg.name} » ignoré${result?.reason ? ` (${result.reason})` : ""}`,
            result?.ok ? "ok" : "error",
          );
        } else if (msg.type === "scan_progress") {
          setScanning(true);
          setProgress({ percent: msg.percent as number, message: msg.message as string });
        } else if (msg.type === "scan_done") {
          const report = msg.report as ScanReport;
          setScan(report);
          setDevices(report.devices);
          setScanning(false);
          setProgress(null);
          pushToast(
            `${report.hosts_found} appareils détectés${report.robot ? " · Roomba identifié" : ""}`,
            "ok",
          );
        }
      };
      ws.onclose = () => {
        if (!closed) timer = window.setTimeout(connect, 2600);
      };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      wsRef.current?.close();
    };
  }, [pushToast, refreshSchedules]);

  useEffect(() => {
    const id = window.setInterval(() => {
      void refreshHistory();
      void refreshSchedules();
    }, 20000);
    return () => clearInterval(id);
  }, [refreshHistory, refreshSchedules]);

  useEffect(() => {
    window.location.hash = tab;
  }, [tab]);

  const startScan = useCallback(async () => {
    if (scanning) return;
    setScanning(true);
    setProgress({ percent: 2, message: "Préparation de l'analyse…" });
    try {
      const report = await api.scan();
      setScan(report);
      setDevices(report.devices);
      pushToast(
        `${report.hosts_found} appareils détectés${report.robot ? " · Roomba identifié" : ""}`,
        "ok",
      );
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : "Analyse impossible", "error");
    } finally {
      setScanning(false);
      setProgress(null);
    }
  }, [scanning, pushToast]);

  const runCommand = useCallback(
    async (name: string, confirm = false) => {
      setBusy(true);
      try {
        await api.command(name, confirm);
        pushToast(`Commande « ${commands[name]?.label ?? name} » envoyée`, "ok");
      } catch (err) {
        pushToast(err instanceof ApiError ? err.message : "Commande refusée", "error");
      } finally {
        setBusy(false);
        setConfirmCmd(null);
      }
    },
    [commands, pushToast],
  );

  const requestCommand = useCallback(
    (name: string) => {
      if (commands[name]?.risky) setConfirmCmd(name);
      else void runCommand(name, true);
    },
    [commands, runCommand],
  );

  const saveCredentials = useCallback(
    async (blid: string, password: string, host: string) => {
      setBusy(true);
      try {
        const res = await api.saveCredentials(blid, password, host);
        setSnapshot(res.snapshot);
        pushToast("Identifiants enregistrés, connexion en cours…", "ok");
      } catch (err) {
        pushToast(err instanceof ApiError ? err.message : "Enregistrement impossible", "error");
      } finally {
        setBusy(false);
      }
    },
    [pushToast],
  );

  const clearCredentials = useCallback(async () => {
    setBusy(true);
    try {
      await api.clearCredentials();
      await refreshRobot();
      pushToast("Identifiants supprimés", "ok");
    } finally {
      setBusy(false);
    }
  }, [pushToast, refreshRobot]);

  const connect = useCallback(async () => {
    setBusy(true);
    try {
      await api.connect();
      await refreshRobot();
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : "Connexion impossible", "error");
    } finally {
      setBusy(false);
    }
  }, [pushToast, refreshRobot]);

  const disconnect = useCallback(async () => {
    setBusy(true);
    try {
      await api.disconnect();
      await refreshRobot();
    } finally {
      setBusy(false);
    }
  }, [refreshRobot]);

  const toggleOnline = useCallback(
    async (v: boolean) => {
      setOnlineVendor(v);
      try {
        await api.saveSettings(v);
      } catch {
        setOnlineVendor(!v);
      }
    },
    [],
  );

  const createSchedule = useCallback(
    async (name: string, days: number[], at: string) => {
      try {
        const r = await api.createSchedule({
          name,
          days,
          at_time: at,
          command: "start",
          enabled: true,
        });
        setSchedules((prev) => [...prev, r.schedule]);
        setNextRuns(r.next);
        pushToast(`Passage « ${r.schedule.name} » programmé`, "ok");
        return true;
      } catch (err) {
        pushToast(err instanceof ApiError ? err.message : "Programmation impossible", "error");
        return false;
      }
    },
    [pushToast],
  );

  const toggleSchedule = useCallback(
    async (id: number, enabled: boolean) => {
      setSchedules((prev) => prev.map((s) => (s.id === id ? { ...s, enabled } : s)));
      try {
        const r = await api.updateSchedule(id, { enabled });
        setNextRuns(r.next);
      } catch (err) {
        pushToast(err instanceof ApiError ? err.message : "Modification impossible", "error");
      } finally {
        void refreshSchedules();
      }
    },
    [pushToast, refreshSchedules],
  );

  const deleteSchedule = useCallback(
    async (id: number) => {
      try {
        await api.deleteSchedule(id);
        setSchedules((prev) => prev.filter((s) => s.id !== id));
        void refreshSchedules();
        pushToast("Passage supprimé", "ok");
      } catch (err) {
        pushToast(err instanceof ApiError ? err.message : "Suppression impossible", "error");
      }
    },
    [pushToast, refreshSchedules],
  );

  const runSchedule = useCallback(
    async (schedule: Schedule) => {
      setBusy(true);
      try {
        await api.runSchedule(schedule.id);
        pushToast(`Passage « ${schedule.name} » envoyé au robot`, "ok");
        await refreshSchedules();
      } catch (err) {
        pushToast(err instanceof ApiError ? err.message : "Lancement impossible", "error");
      } finally {
        setBusy(false);
        setConfirmSchedule(null);
      }
    },
    [pushToast, refreshSchedules],
  );

  const current = useMemo(() => TABS.find((t) => t.id === tab) ?? TABS[0], [tab]);
  const status = snapshot?.status ?? "offline";

  return (
    <div className="app">
      <div className="aurora" aria-hidden>
        <span className="blob b1" />
        <span className="blob b2" />
        <span className="blob b3" />
        <span className="grain" />
      </div>

      <aside className="sidebar glass">
        <div className="brand">
          <div className="brand-mark">R</div>
          <div>
            <strong>ROO·LAB</strong>
            <span>Roomba j7+</span>
          </div>
        </div>
        <nav>
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`nav-item${tab === t.id ? " active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              <span className="nav-icon">{t.icon}</span>
              <span>{t.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className={`conn ${snapshot?.connected ? "on" : ""}`}>
            <span className="conn-dot" />
            <div>
              <strong>{snapshot?.connected ? "Robot connecté" : statusText(status)}</strong>
              <span>{snapshot?.link?.host ?? "MQTT/TLS local"}</span>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>{current.title}</h1>
            <p>{current.sub}</p>
          </div>
          <div className="topbar-actions">
            <span className="host-chip">
              <span className={`live-dot${snapshot?.connected ? " on" : ""}`} />
              {snapshot?.connected ? "temps réel" : "hors ligne"}
            </span>
            <Button variant="glass" onClick={() => void startScan()} disabled={scanning}>
              {scanning ? "Analyse…" : "Analyser le réseau"}
            </Button>
          </div>
        </header>

        {tab === "dashboard" && (
          <Dashboard
            snapshot={snapshot}
            scan={scan}
            missions={missions}
            events={events}
            telemetry={telemetry}
            stats={stats}
            scanning={scanning}
            progress={progress}
            onScan={() => void startScan()}
            goTo={setTab}
          />
        )}
        {tab === "network" && (
          <Network
            scan={scan}
            devices={devices}
            scanning={scanning}
            progress={progress}
            onScan={() => void startScan()}
            onlineVendor={onlineVendor}
            onToggleOnline={(v) => void toggleOnline(v)}
          />
        )}
        {tab === "control" && (
          <Control
            snapshot={snapshot}
            commands={commands}
            busy={busy}
            onCommand={requestCommand}
            goTo={setTab}
          />
        )}
        {tab === "planning" && (
          <Planning
            schedules={schedules}
            next={nextRuns}
            connected={snapshot?.connected ?? false}
            busy={busy}
            onCreate={createSchedule}
            onToggle={(id, enabled) => void toggleSchedule(id, enabled)}
            onDelete={(id) => void deleteSchedule(id)}
            onRun={(schedule) => setConfirmSchedule(schedule)}
          />
        )}
        {tab === "map" && <MapPage snapshot={snapshot} telemetry={telemetry} />}
        {tab === "settings" && (
          <Settings
            snapshot={snapshot}
            scan={scan}
            busy={busy}
            onlineVendor={onlineVendor}
            ipHint={snapshot?.ip_hint ?? scan?.robot?.ip ?? ""}
            onSave={saveCredentials}
            onClear={() => void clearCredentials()}
            onConnect={() => void connect()}
            onDisconnect={() => void disconnect()}
            onToggleOnline={(v) => void toggleOnline(v)}
          />
        )}
      </main>

      <nav className="mobile-nav glass">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => setTab(t.id)}
          >
            <span>{t.icon}</span>
            {t.label.split(" ")[0]}
          </button>
        ))}
      </nav>

      <Toasts items={toasts} onDismiss={(id) => setToasts((t) => t.filter((x) => x.id !== id))} />

      <Modal
        open={confirmCmd !== null}
        title="Confirmer la commande"
        onClose={() => setConfirmCmd(null)}
      >
        <p className="modal-text">
          {confirmCmd ? commands[confirmCmd]?.label : ""} — cette action modifie l'état réel du
          robot. Elle sera journalisée dans l'historique local.
        </p>
        <div className="modal-actions">
          <Button variant="ghost" onClick={() => setConfirmCmd(null)}>
            Annuler
          </Button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => confirmCmd && void runCommand(confirmCmd, true)}
          >
            Confirmer
          </Button>
        </div>
      </Modal>

      <Modal
        open={confirmSchedule !== null}
        title="Lancer ce passage maintenant ?"
        onClose={() => setConfirmSchedule(null)}
      >
        <p className="modal-text">
          Le robot va démarrer un nettoyage immédiatement. Cette action est indépendante de
          l'horaire programmé et sera journalisée.
        </p>
        <div className="modal-actions">
          <Button variant="ghost" onClick={() => setConfirmSchedule(null)}>
            Annuler
          </Button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => confirmSchedule && void runSchedule(confirmSchedule)}
          >
            Démarrer
          </Button>
        </div>
      </Modal>
    </div>
  );
}
