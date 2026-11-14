import type { AppEvent, Mission, RobotSnapshot, ScanReport, TelemetrySample } from "../types";
import { BatteryRing, Button, EmptyState, Glass, Pill, SectionTitle, Sparkline, Stat } from "../components/ui";
import { fmtDate, fmtDuration, fmtNumber, fmtRelative, statusText } from "../lib/format";
import type { Tab } from "../App";

const TONE: Record<string, "ok" | "warn" | "error" | "info" | "neutral"> = {
  docked: "ok",
  charging: "ok",
  cleaning: "info",
  paused: "warn",
  returning: "info",
  emptying: "info",
  stopped: "warn",
  error: "error",
  bin_full: "warn",
  idle: "neutral",
  unknown: "neutral",
  connected: "ok",
  offline: "error",
  unconfigured: "warn",
  connecting: "info",
  reconnecting: "warn",
  auth_error: "error",
};

export function Dashboard({
  snapshot,
  scan,
  missions,
  events,
  telemetry,
  stats,
  scanning,
  progress,
  onScan,
  goTo,
}: {
  snapshot: RobotSnapshot | null;
  scan: ScanReport | null;
  missions: Mission[];
  events: AppEvent[];
  telemetry: TelemetrySample[];
  stats: { missions: number; seconds: number; sqft: number; avg_seconds: number };
  scanning: boolean;
  progress: { percent: number; message: string } | null;
  onScan: () => void;
  goTo: (t: Tab) => void;
}) {
  const status = snapshot?.status ?? "offline";
  const statusLabel = snapshot?.status_label ?? status;
  const tone = TONE[status] ?? (snapshot?.connected ? "ok" : "neutral");
  const battery = snapshot?.battery ?? null;
  const series = telemetry
    .filter((s) => s.battery !== null && s.battery !== undefined)
    .slice(-90)
    .map((s) => s.battery as number);
  const last = missions[0];
  const bin = snapshot?.bin;
  const connected = snapshot?.connected;

  return (
    <div className="stack">
      <Glass className="hero">
        <div className="hero-halo" />
        <div className="hero-left">
          <div className={`status-orb ${tone}`}>
            <span className="orb-core" />
            <span className="orb-ring" />
          </div>
          <div>
            <div className="eyebrow">iRobot Roomba j7+ · j755840</div>
            <h2 className="hero-title">
              {snapshot?.identity?.name || scan?.robot?.label || "Roomba"}
            </h2>
            <div className="hero-tags">
              <Pill tone={tone} dot>
                {statusText(statusLabel)}
              </Pill>
              {snapshot?.mission?.cycle === "clean" && (
                <Pill tone="info">mission #{snapshot.mission.nMssn ?? "—"}</Pill>
              )}
              {!snapshot?.configured && <Pill tone="warn">non appairé</Pill>}
            </div>
            <p className="hero-sub">
              {connected
                ? `Liaison locale MQTT/TLS établie avec ${snapshot?.link?.host ?? "le robot"}.`
                : snapshot?.configured
                  ? snapshot?.link?.last_error ||
                    "Identifiants présents — tentative de connexion locale."
                  : "Analyse réseau terminée. L'appairage local reste à effectuer pour lire l'état réel."}
            </p>
          </div>
        </div>
        <div className="hero-right">
          <BatteryRing
            value={battery}
            charging={status === "charging" || status === "docked"}
            label={battery === null ? "non connecté" : "batterie"}
          />
        </div>
      </Glass>

      <div className="chip-row">
        <div className="mini-chip">
          <span>Connexion</span>
          <strong>{connected ? "MQTT/TLS · 8883" : "hors ligne"}</strong>
        </div>
        <div className="mini-chip">
          <span>Station Clean Base</span>
          <strong>
            {snapshot?.dock?.known ? "détectée" : snapshot?.configured ? "inconnue" : "—"}
          </strong>
        </div>
        <div className="mini-chip">
          <span>Bac</span>
          <strong>
            {bin ? (bin.full ? "plein" : bin.present ? "en place" : "absent") : "—"}
          </strong>
        </div>
        <div className="mini-chip">
          <span>Signal Wi-Fi</span>
          <strong>
            {snapshot?.signal?.rssi !== undefined ? `${snapshot.signal.rssi} dBm` : "—"}
          </strong>
        </div>
      </div>

      {!snapshot?.configured && (
        <Glass className="onboard">
          <div className="onboard-head">
            <div>
              <span className="eyebrow">Prochaine étape</span>
              <h3>Activer le contrôle local</h3>
            </div>
            <Pill tone="info">1 seule fois</Pill>
          </div>
          <p className="muted">
            Le j7+ n'expose pas de mot de passe sur le réseau : il faut récupérer la paire
            <strong> BLID / mot de passe local</strong> depuis votre compte iRobot, puis ROO-LAB
            parle directement au robot en MQTT/TLS — sans passer par le cloud ensuite.
          </p>
          <div className="steps">
            <div className="step">
              <span>1</span>
              <div>
                <strong>Identifiants</strong>
                <p>Récupérés une fois, chiffrés sur ce PC (DPAPI).</p>
              </div>
            </div>
            <div className="step">
              <span>2</span>
              <div>
                <strong>Connexion locale</strong>
                <p>MQTT sur le port 8883 du robot, chiffré en TLS.</p>
              </div>
            </div>
            <div className="step">
              <span>3</span>
              <div>
                <strong>Tableau de bord réel</strong>
                <p>Batterie, missions, position, station — sans rien inventer.</p>
              </div>
            </div>
          </div>
          <div className="onboard-actions">
            <Button variant="primary" onClick={() => goTo("settings")}>
              Configurer l'appairage
            </Button>
            <Button variant="ghost" onClick={() => goTo("network")}>
              Voir le réseau
            </Button>
          </div>
        </Glass>
      )}

      {scan?.robot && !snapshot?.configured && (
        <Glass className="detected">
          <SectionTitle
            title="Robot identifié sur le réseau"
            aside={<Pill tone="ok">phase 1 validée</Pill>}
          />
          <div className="kv-grid">
            <div><span>Adresse IP</span><strong>{scan.robot.ip}</strong></div>
            <div><span>Adresse MAC</span><strong className="mono">{scan.robot.mac ?? "—"}</strong></div>
            <div><span>Constructeur</span><strong>{scan.robot.vendor ?? "—"}</strong></div>
            <div><span>Service local</span><strong>MQTT/TLS 8883</strong></div>
            <div><span>Certificat</span><strong className="mono small">{scan.robot.tls?.common_name ?? "—"}</strong></div>
            <div><span>Sous-réseau</span><strong className="mono">{scan.subnet}</strong></div>
          </div>
          <ul className="evidence">
            {scan.robot.evidence.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </Glass>
      )}

      <div className="grid-4">
        <Glass className="stat-card">
          <Stat label="Dernière mission" value={last ? fmtRelative(last.started_at) : "—"} hint={last ? fmtDuration(last.duration_s) : "aucune donnée"} />
        </Glass>
        <Glass className="stat-card">
          <Stat label="Surface cumulée" value={`${fmtNumber(stats.sqft)} ft²`} hint={`${stats.missions} mission(s)`} />
        </Glass>
        <Glass className="stat-card">
          <Stat label="Temps cumulé" value={fmtDuration(stats.seconds)} hint="historisé localement" />
        </Glass>
        <Glass className="stat-card">
          <Stat
            label="Mission en cours"
            value={snapshot?.mission?.phase === "run" ? `${snapshot.mission.sqft ?? 0} ft²` : "—"}
            hint={snapshot?.mission?.phase === "run" ? `${snapshot.mission.mssnM ?? 0} min` : "au repos"}
          />
        </Glass>
      </div>

      <div className="grid-2">
        <Glass>
          <SectionTitle
            title="Batterie"
            aside={<span className="muted small">{series.length ? "180 dernières minutes" : "en attente"}</span>}
          />
          {series.length > 1 ? (
            <>
              <div className="chart-wrap">
                <Sparkline values={series} min={0} max={100} height={72} />
              </div>
              <div className="chart-legend">
                <span>min {Math.min(...series)}%</span>
                <span>max {Math.max(...series)}%</span>
              </div>
            </>
          ) : (
            <div className="chart-empty">
              La courbe apparaîtra dès la première connexion locale au robot.
            </div>
          )}
        </Glass>

        <Glass>
          <SectionTitle
            title="Analyse réseau"
            aside={
              <Button variant="ghost" onClick={onScan} disabled={scanning}>
                {scanning ? "en cours" : "relancer"}
              </Button>
            }
          />
          {scanning && progress ? (
            <div className="progress-block">
              <div className="progress-bar">
                <span style={{ width: `${progress.percent}%` }} />
              </div>
              <p className="muted small">{progress.message}</p>
            </div>
          ) : scan ? (
            <div className="scan-summary">
              <div className="scan-big">{scan.hosts_found}</div>
              <div>
                <strong>appareils détectés</strong>
                <p className="muted small">
                  {scan.subnet} · en {scan.duration_s.toFixed(1)} s
                </p>
              </div>
              <div className="scan-split">
                <span>{scan.devices.filter((d) => d.kind === "robot").length} robot</span>
                <span>{scan.devices.filter((d) => d.vendor).length} constructeurs identifiés</span>
                <span>{scan.devices.filter((d) => d.ports.length).length} avec services</span>
              </div>
            </div>
          ) : (
            <EmptyState icon="⌁" title="Aucune analyse">
              Lancez une analyse pour découvrir les appareils du réseau local.
            </EmptyState>
          )}
        </Glass>
      </div>

      <div className="grid-2">
        <Glass>
          <SectionTitle title="Dernières missions" aside={<span className="muted small">SQLite local</span>} />
          {missions.length === 0 ? (
            <EmptyState icon="◷" title="Aucune mission enregistrée">
              L'historique se remplit à partir des états reçus du robot.
            </EmptyState>
          ) : (
            <ul className="list">
              {missions.slice(0, 6).map((m) => (
                <li key={m.id} className="list-row">
                  <div className="list-main">
                    <strong>Mission #{m.number ?? m.id}</strong>
                    <span className="muted small">{fmtDate(m.started_at)}</span>
                  </div>
                  <div className="list-meta">
                    <span>{fmtDuration(m.duration_s)}</span>
                    <span className="muted small">{fmtNumber(m.area_sqft)} ft²</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Glass>

        <Glass>
          <SectionTitle title="Dernière activité" aside={<span className="muted small">journal</span>} />
          {events.length === 0 ? (
            <EmptyState icon="◌" title="Journal vide">
              Les connexions, commandes et alertes seront tracées ici.
            </EmptyState>
          ) : (
            <ul className="feed">
              {events.slice(0, 7).map((e) => (
                <li key={e.id} className={`feed-row ${e.level}`}>
                  <span className="feed-dot" />
                  <div>
                    <strong>{e.message}</strong>
                    <span className="muted small">{fmtRelative(e.ts)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Glass>
      </div>
    </div>
  );
}
