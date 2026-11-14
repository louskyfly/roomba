import { useMemo, useState } from "react";
import type { Schedule } from "../types";
import { Button, EmptyState, Glass, Modal, Pill, SectionTitle, Switch } from "../components/ui";

const DAYS = ["L", "M", "M", "J", "V", "S", "D"];
const DAY_NAMES = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];

function daysLabel(days: number[]): string {
  const sorted = [...days].sort((a, b) => a - b);
  if (sorted.length === 7) return "tous les jours";
  if (sorted.length === 5 && sorted.every((d, i) => d === i)) return "en semaine";
  if (sorted.length === 2 && sorted[0] === 5 && sorted[1] === 6) return "le week-end";
  return sorted.map((d) => DAY_NAMES[d]).join(", ");
}

function nextLabel(ts?: number): string {
  if (!ts) return "—";
  const date = new Date(ts * 1000);
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  const hour = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  if (sameDay) return `aujourd'hui à ${hour}`;
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  if (date.toDateString() === tomorrow.toDateString()) return `demain à ${hour}`;
  const weekday = date.toLocaleDateString("fr-FR", { weekday: "long" });
  return `${weekday} à ${hour}`;
}

function lastRunLabel(schedule: Schedule): string {
  if (!schedule.last_run_at) return "jamais exécuté";
  const date = new Date(schedule.last_run_at * 1000);
  const stamp = date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${stamp} · ${schedule.last_result ?? "—"}`;
}

export function Planning({
  schedules,
  next,
  connected,
  busy,
  onCreate,
  onToggle,
  onDelete,
  onRun,
}: {
  schedules: Schedule[];
  next: Record<string, number>;
  connected: boolean;
  busy: boolean;
  onCreate: (name: string, days: number[], at: string) => Promise<boolean>;
  onToggle: (id: number, enabled: boolean) => void;
  onDelete: (id: number) => void;
  onRun: (schedule: Schedule) => void;
}) {
  const [name, setName] = useState("");
  const [days, setDays] = useState<number[]>([0, 2, 4]);
  const [at, setAt] = useState("10:00");
  const [confirmDelete, setConfirmDelete] = useState<Schedule | null>(null);

  const active = useMemo(() => schedules.filter((s) => s.enabled).length, [schedules]);

  const toggleDay = (index: number) => {
    setDays((current) =>
      current.includes(index) ? current.filter((d) => d !== index) : [...current, index].sort(),
    );
  };

  const submit = async () => {
    if (!name.trim() || !days.length || !at) return;
    const ok = await onCreate(name.trim(), days, at);
    if (ok) {
      setName("");
      setDays([0, 2, 4]);
      setAt("10:00");
    }
  };

  return (
    <div className="stack">
      <Glass className="planning-head">
        <div>
          <span className="eyebrow">Phase 4 · programmation</span>
          <h2>Nettoyages programmés</h2>
          <p className="muted">
            {active
              ? `${active} passage${active > 1 ? "s" : ""} actif${active > 1 ? "s" : ""} · heure locale du PC`
              : "Aucun passage actif pour le moment"}
          </p>
        </div>
        <Pill tone={connected ? "ok" : "warn"} dot>
          {connected ? "robot en ligne" : "robot hors ligne"}
        </Pill>
      </Glass>

      <div className="grid-planning">
        <Glass>
          <SectionTitle title="Nouveau passage" />
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <label className="field">
              <span>Nom</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nettoyage du salon"
                maxLength={59}
              />
            </label>

            <div className="field">
              <span>Jours</span>
              <div className="day-picker">
                {DAYS.map((label, index) => (
                  <button
                    key={index}
                    type="button"
                    className={`day${days.includes(index) ? " on" : ""}`}
                    aria-pressed={days.includes(index)}
                    onClick={() => toggleDay(index)}
                    title={DAY_NAMES[index]}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <span className="switch-hint">{days.length ? daysLabel(days) : "choisir au moins un jour"}</span>
            </div>

            <label className="field">
              <span>Heure</span>
              <input type="time" value={at} onChange={(e) => setAt(e.target.value)} required />
            </label>

            <div className="form-actions">
              <Button type="submit" variant="primary" disabled={busy || !name.trim() || !days.length}>
                Programmer
              </Button>
            </div>
          </form>
        </Glass>

        <Glass>
          <SectionTitle
            title="Planning"
            aside={<span className="muted small">{schedules.length} entrée{schedules.length > 1 ? "s" : ""}</span>}
          />
          {schedules.length === 0 ? (
            <EmptyState icon="◷" title="Rien de programmé">
              <p>
                Créez un passage à gauche. Il sera envoyé au robot uniquement s'il est connecté au
                broker local au moment prévu.
              </p>
            </EmptyState>
          ) : (
            <ul className="schedule-list">
              {schedules.map((schedule) => (
                <li key={schedule.id} className={`schedule${schedule.enabled ? "" : " off"}`}>
                  <div className="schedule-main">
                    <div className="schedule-time mono">{schedule.at_time}</div>
                    <div className="schedule-info">
                      <strong>{schedule.name}</strong>
                      <span className="muted small">
                        {daysLabel(schedule.days)} · prochain :{" "}
                        {schedule.enabled ? nextLabel(next[String(schedule.id)]) : "désactivé"}
                      </span>
                      <span className="schedule-last">{lastRunLabel(schedule)}</span>
                    </div>
                  </div>
                  <div className="schedule-actions">
                    <Switch
                      checked={schedule.enabled}
                      onChange={(v) => onToggle(schedule.id, v)}
                      label=""
                    />
                    <Button
                      variant="ghost"
                      onClick={() => onRun(schedule)}
                      disabled={busy || !connected}
                    >
                      Lancer
                    </Button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label="Supprimer"
                      onClick={() => setConfirmDelete(schedule)}
                    >
                      ✕
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small note">
            Un passage n'entraîne jamais de démarrage sans confirmation : le déclenchement
            automatique est écrit dans le journal local. Si le robot est hors ligne au moment
            prévu, le passage est marqué « ignoré » et n'est pas rejoué.
          </p>
        </Glass>
      </div>

      <Modal
        open={confirmDelete !== null}
        title="Supprimer ce passage ?"
        onClose={() => setConfirmDelete(null)}
      >
        <p className="modal-text">
          « {confirmDelete?.name} » sera retiré du planning. Le robot et son historique de
          missions ne sont pas modifiés.
        </p>
        <div className="modal-actions">
          <Button variant="ghost" onClick={() => setConfirmDelete(null)}>
            Annuler
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              if (confirmDelete) onDelete(confirmDelete.id);
              setConfirmDelete(null);
            }}
          >
            Supprimer
          </Button>
        </div>
      </Modal>
    </div>
  );
}
