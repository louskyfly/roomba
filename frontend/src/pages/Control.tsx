import type { CommandMeta, RobotSnapshot } from "../types";
import { Button, EmptyState, Glass, Pill, SectionTitle, Stat } from "../components/ui";
import { fmtDuration, statusText } from "../lib/format";
import type { Tab } from "../App";

const MAIN: Array<{ id: string; icon: string; hint: string; cls?: string }> = [
  { id: "pause", icon: "❚❚", hint: "Suspendre" },
  { id: "start", icon: "▶", hint: "Démarrer / nettoyer", cls: "main" },
  { id: "resume", icon: "↻", hint: "Reprendre" },
];

const SECONDARY: Array<{ id: string; icon: string; hint: string }> = [
  { id: "stop", icon: "■", hint: "Arrêter la mission" },
  { id: "dock", icon: "⌂", hint: "Retour à la base" },
  { id: "find", icon: "♪", hint: "Faire sonner" },
  { id: "evac", icon: "⇪", hint: "Vider le bac" },
];

export function Control({
  snapshot,
  commands,
  busy,
  onCommand,
  goTo,
}: {
  snapshot: RobotSnapshot | null;
  commands: CommandMeta;
  busy: boolean;
  onCommand: (name: string) => void;
  goTo: (t: Tab) => void;
}) {
  if (!snapshot?.configured) {
    return (
      <Glass>
        <EmptyState icon="⏻" title="Contrôle verrouillé">
          <p>
            Le j7+ n'accepte une connexion locale qu'après authentification MQTT avec la paire
            BLID / mot de passe de votre robot. Aucune commande n'est envoyée sans cette étape.
          </p>
          <p className="muted small">
            Une fois appairé, vous pourrez envoyer les commandes locales (nettoyer, pause, retour
            base, vidage…). Le j7+ ne permet pas de conduite « roue par roue » en temps réel : la
            télécommande pilote les actions de mission exposées par le robot.
          </p>
          <Button variant="primary" onClick={() => goTo("settings")}>
            Configurer l'appairage
          </Button>
        </EmptyState>
      </Glass>
    );
  }

  const connected = snapshot.connected;
  const mission = snapshot.mission;
  const battery = snapshot.battery;
  const running = snapshot.status_label === "cleaning" || snapshot.status_label === "returning";

  return (
    <div className="stack">
      <Glass className="control-head">
        <div>
          <span className="eyebrow">Télécommande locale</span>
          <h2>{connected ? "Robot prêt" : statusText(snapshot.status)}</h2>
          <p className="muted">
            {connected
              ? `Connecté à ${snapshot.link?.host} · ${snapshot.link?.messages ?? 0} messages reçus`
              : snapshot.link?.last_error || "Tentative de connexion au broker MQTT du robot."}
          </p>
        </div>
        <Pill tone={connected ? "ok" : "warn"} dot>
          {connected ? "MQTT/TLS actif" : "hors ligne"}
        </Pill>
      </Glass>

      <div className="grid-4">
        <Glass className="stat-card"><Stat label="Batterie" value={battery !== null && battery !== undefined ? `${battery}%` : "—"} hint={snapshot.dock?.known ? "sur station" : "hors station"} /></Glass>
        <Glass className="stat-card"><Stat label="Phase" value={statusText(snapshot.status_label ?? "unknown")} hint={mission?.cycle ?? "—"} /></Glass>
        <Glass className="stat-card"><Stat label="Surface mission" value={mission?.sqft !== undefined ? `${mission.sqft} ft²` : "—"} hint={mission?.nMssn ? `mission #${mission.nMssn}` : "—"} /></Glass>
        <Glass className="stat-card"><Stat label="Durée" value={mission?.mssnM !== undefined ? fmtDuration(mission.mssnM * 60) : "—"} hint="temps robot" /></Glass>
      </div>

      <Glass className="remote">
        <SectionTitle
          title="Télécommande"
          aside={
            <span className="muted small">
              {connected ? (running ? "mission en cours" : "en attente") : "connexion requise"}
            </span>
          }
        />
        <div className="remote-pad">
          <div className="remote-main">
            {MAIN.map((c) => {
              const meta = commands[c.id];
              if (!meta) return null;
              return (
                <button
                  key={c.id}
                  className={`rc-btn ${c.cls ?? ""}${meta.risky ? " risky" : ""}`}
                  disabled={!connected || busy}
                  onClick={() => onCommand(c.id)}
                  title={c.hint}
                >
                  <span className="rc-icon">{c.icon}</span>
                  <span className="rc-label">{meta.label}</span>
                </button>
              );
            })}
          </div>
          <div className="remote-secondary">
            {SECONDARY.map((c) => {
              const meta = commands[c.id];
              if (!meta) return null;
              return (
                <button
                  key={c.id}
                  className={`rc-btn small${meta.risky ? " risky" : ""}`}
                  disabled={!connected || busy}
                  onClick={() => onCommand(c.id)}
                  title={c.hint}
                >
                  <span className="rc-icon">{c.icon}</span>
                  <span className="rc-label">{meta.label}</span>
                  {meta.risky && <span className="rc-sub">confirmation</span>}
                </button>
              );
            })}
          </div>
        </div>
        {!connected && (
          <p className="muted small center">
            Les commandes restent désactivées tant que la liaison MQTT/TLS n'est pas établie.
          </p>
        )}
      </Glass>

      <div className="grid-2">
        <Glass>
          <SectionTitle title="Position temps réel" />
          {snapshot.pose?.point ? (
            <div className="pose-live">
              <div><span>X</span><strong className="mono">{snapshot.pose.point.x}</strong></div>
              <div><span>Y</span><strong className="mono">{snapshot.pose.point.y}</strong></div>
              <div><span>Cap</span><strong className="mono">{snapshot.pose.theta}°</strong></div>
            </div>
          ) : (
            <p className="muted small">
              Aucune position reçue. Le robot ne publie `pose` que pendant une mission, et
              certains firmwares la réservent au cloud.
            </p>
          )}
          <p className="muted small note">
            Trame brute conservée pour la carte : chaque échantillon est stocké toutes les 4 s.
          </p>
        </Glass>

        <Glass>
          <SectionTitle title="Station & consommables" />
          <div className="kv-grid tight">
            <div><span>Station</span><strong>{snapshot.dock?.known ? "détectée" : "non détectée"}</strong></div>
            <div><span>Bac</span><strong>{snapshot.bin ? (snapshot.bin.full ? "plein" : snapshot.bin.present ? "en place" : "absent") : "—"}</strong></div>
            <div><span>Signal</span><strong>{snapshot.signal?.rssi !== undefined ? `${snapshot.signal.rssi} dBm` : "—"}</strong></div>
            <div><span>Dernière commande</span><strong>{snapshot.last_command?.command ?? "—"}</strong></div>
          </div>
        </Glass>
      </div>
    </div>
  );
}
