import { useMemo } from "react";
import type { RobotSnapshot, TelemetrySample } from "../types";
import { EmptyState, Glass, Pill, SectionTitle, Stat } from "../components/ui";

export function MapPage({
  snapshot,
  telemetry,
}: {
  snapshot: RobotSnapshot | null;
  telemetry: TelemetrySample[];
}) {
  const points = useMemo(
    () =>
      telemetry
        .filter((s) => s.x !== null && s.x !== undefined && s.y !== null && s.y !== undefined)
        .map((s) => ({ x: s.x as number, y: s.y as number, ts: s.ts })),
    [telemetry],
  );

  const geometry = useMemo(() => {
    if (points.length < 2) return null;
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const w = Math.max(maxX - minX, 600);
    const h = Math.max(maxY - minY, 400);
    const pad = 60;
    const width = w + pad * 2;
    const height = h + pad * 2;
    const path = points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${(p.x - minX + pad).toFixed(1)} ${(h - (p.y - minY) + pad).toFixed(1)}`)
      .join(" ");
    let distance = 0;
    for (let i = 1; i < points.length; i++) {
      distance += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
    }
    return { width, height, path, minX, minY, w, h, distance, first: points[0], last: points[points.length - 1] };
  }, [points]);

  const rooms = snapshot?.map?.maps?.[0]?.rooms ?? [];

  return (
    <div className="stack">
      <Glass className="map-card">
        <SectionTitle
          title="Trajectoire enregistrée"
          aside={
            <div className="map-badges">
              <Pill tone={points.length ? "ok" : "neutral"} dot>
                {points.length ? `${points.length} points` : "aucune donnée"}
              </Pill>
              {snapshot?.map?.maps?.length ? <Pill tone="info">{snapshot.map.maps.length} carte(s)</Pill> : null}
            </div>
          }
        />
        {geometry ? (
          <>
            <div className="map-canvas">
              <svg viewBox={`0 0 ${geometry.width} ${geometry.height}`} preserveAspectRatio="xMidYMid meet">
                <defs>
                  <linearGradient id="pathGrad" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.15" />
                    <stop offset="55%" stopColor="var(--accent)" stopOpacity="0.9" />
                    <stop offset="100%" stopColor="var(--accent-2)" stopOpacity="1" />
                  </linearGradient>
                  <filter id="glow">
                    <feGaussianBlur stdDeviation="6" result="b" />
                    <feMerge>
                      <feMergeNode in="b" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>
                <g className="map-grid">
                  {Array.from({ length: 12 }).map((_, i) => (
                    <line key={`v${i}`} x1={(i * geometry.width) / 12} y1={0} x2={(i * geometry.width) / 12} y2={geometry.height} />
                  ))}
                  {Array.from({ length: 8 }).map((_, i) => (
                    <line key={`h${i}`} x1={0} y1={(i * geometry.height) / 8} x2={geometry.width} y2={(i * geometry.height) / 8} />
                  ))}
                </g>
                <path d={geometry.path} fill="none" stroke="url(#pathGrad)" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round" filter="url(#glow)" />
                <circle
                  cx={geometry.first.x - geometry.minX + 60}
                  cy={geometry.h - (geometry.first.y - geometry.minY) + 60}
                  r="9"
                  className="map-start"
                />
                <circle
                  cx={geometry.last.x - geometry.minX + 60}
                  cy={geometry.h - (geometry.last.y - geometry.minY) + 60}
                  r="12"
                  className="map-now"
                />
              </svg>
            </div>
            <div className="map-legend">
              <span><i className="dot start" /> départ</span>
              <span><i className="dot now" /> position actuelle</span>
              <span className="muted">distance ~ {Math.round(geometry.distance / 100)} m</span>
            </div>
          </>
        ) : (
          <EmptyState icon="◇" title="Aucune trajectoire locale">
            <p>
              Le j7+ ne diffuse un plan lisible qu'à travers son application ou le cloud.
              ROO-LAB n'affiche que ce que le robot publie réellement en local : la trame
              <code> pose</code>, échantillonnée pendant les missions.
            </p>
            <p className="muted small">
              Dès qu'une mission sera observée avec des coordonnées, la trajectoire apparaîtra ici.
              Aucune carte n'est inventée.
            </p>
          </EmptyState>
        )}
      </Glass>

      <div className="grid-2">
        <Glass>
          <SectionTitle title="Pièces connues" aside={<span className="muted small">métadonnées robot</span>} />
          {rooms.length ? (
            <div className="room-chips">
              {rooms.map((r) => (
                <span key={r.id ?? r.name} className="room-chip">
                  {r.name ?? `Pièce ${r.id}`}
                  <em>{r.type}</em>
                </span>
              ))}
            </div>
          ) : (
            <p className="muted small">
              Aucune liste de pièces reçue. Elle provient du champ <code>pmaps</code> de l'état
              robot, quand le firmware l'expose en local.
            </p>
          )}
        </Glass>
        <Glass>
          <SectionTitle title="Ce que le robot expose" />
          <div className="kv-grid tight">
            <div><span>Position brute</span><strong>{snapshot?.pose?.point ? "disponible" : "non reçue"}</strong></div>
            <div><span>Cartes (pmaps)</span><strong>{snapshot?.map?.maps?.length ?? 0}</strong></div>
            <div><span>Échantillons</span><strong>{points.length}</strong></div>
            <div><span>Fenêtre</span><strong>3 h glissantes</strong></div>
          </div>
          <p className="muted small note">
            Une image de plan n'est pas exposée par le broker local du j7+. ROO-LAB ne la
            fabrique pas et n'invente aucune pièce.
          </p>
        </Glass>
      </div>

      <Glass>
        <SectionTitle title="Dernières positions" />
        {points.length ? (
          <div className="table-wrap">
            <table className="devices">
              <thead>
                <tr><th>Heure</th><th>X</th><th>Y</th><th>Cap</th></tr>
              </thead>
              <tbody>
                {telemetry
                  .filter((s) => s.x !== null && s.y !== null)
                  .slice(-8)
                  .reverse()
                  .map((s) => (
                    <tr key={s.id}>
                      <td>{new Date(s.ts * 1000).toLocaleTimeString("fr-FR")}</td>
                      <td className="mono">{s.x}</td>
                      <td className="mono">{s.y}</td>
                      <td className="mono">{s.theta}°</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted small">En attente de télémétrie.</p>
        )}
      </Glass>
    </div>
  );
}
