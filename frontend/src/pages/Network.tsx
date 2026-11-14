import { useMemo, useState } from "react";
import type { Device, ScanReport } from "../types";
import { Button, EmptyState, Glass, Modal, Pill, SectionTitle, Switch } from "../components/ui";
import { KIND_ICON } from "../lib/format";

export function Network({
  scan,
  devices,
  scanning,
  progress,
  onScan,
  onlineVendor,
  onToggleOnline,
}: {
  scan: ScanReport | null;
  devices: Device[];
  scanning: boolean;
  progress: { percent: number; message: string } | null;
  onScan: () => void;
  onlineVendor: boolean;
  onToggleOnline: (v: boolean) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "robot" | "known" | "services">("all");
  const [selected, setSelected] = useState<Device | null>(null);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return devices.filter((d) => {
      if (filter === "robot" && d.kind !== "robot") return false;
      if (filter === "known" && !d.vendor) return false;
      if (filter === "services" && d.ports.length === 0) return false;
      if (!q) return true;
      return [d.label, d.ip, d.mac, d.vendor, d.hostname]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q));
    });
  }, [devices, query, filter]);

  return (
    <div className="stack">
      <Glass className="net-head">
        <div className="net-iface">
          <span className="eyebrow">Interface locale</span>
          <h2>{scan?.interface.name ?? "Recherche…"}</h2>
          <div className="iface-grid">
            <div><span>Adresse</span><strong className="mono">{scan?.interface.ip ?? "—"}</strong></div>
            <div><span>Sous-réseau</span><strong className="mono">{scan?.subnet ?? "—"}</strong></div>
            <div><span>Passerelle</span><strong className="mono">{scan?.interface.gateway ?? "—"}</strong></div>
            <div><span>MAC</span><strong className="mono small">{scan?.interface.mac ?? "—"}</strong></div>
          </div>
        </div>
        <div className="net-action">
          <Button variant="primary" onClick={onScan} disabled={scanning}>
            {scanning ? "Analyse en cours…" : "Analyser le réseau"}
          </Button>
          <span className="muted small">
            ARP + mDNS + SSDP + ports TCP, lecture seule
          </span>
        </div>
      </Glass>

      {scanning && progress && (
        <Glass className="scan-live">
          <div className="scan-live-head">
            <strong>{progress.message}</strong>
            <span className="mono">{progress.percent}%</span>
          </div>
          <div className="progress-bar">
            <span style={{ width: `${progress.percent}%` }} />
          </div>
        </Glass>
      )}

      {scan?.robot && (
        <Glass className="robot-banner">
          <div className="robot-banner-left">
            <div className="kind-badge robot">◉</div>
            <div>
              <span className="eyebrow">Appareil iRobot confirmé</span>
              <h3>{scan.robot.label}</h3>
              <p className="muted small">
                {scan.robot.ip} · {scan.robot.vendor} · MQTT/TLS 8883
              </p>
            </div>
          </div>
          <div className="robot-banner-right">
            <Pill tone="ok" dot>identifié</Pill>
            <Button variant="ghost" onClick={() => setSelected(scan.robot)}>
              Détails
            </Button>
          </div>
        </Glass>
      )}

      <Glass>
        <SectionTitle
          title="Appareils du réseau"
          aside={<span className="muted small">{shown.length} / {devices.length}</span>}
        />
        <div className="toolbar">
          <div className="segmented">
            {(
              [
                ["all", "Tous"],
                ["robot", "Robot"],
                ["known", "Constructeur"],
                ["services", "Services"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                className={filter === id ? "on" : ""}
                onClick={() => setFilter(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <input
            className="search"
            placeholder="Rechercher IP, MAC, nom…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {shown.length === 0 ? (
          <EmptyState icon="⌁" title={devices.length ? "Aucun résultat" : "Aucun appareil"}>
            {devices.length
              ? "Modifiez le filtre ou la recherche."
              : "Lancez une analyse pour remplir l'inventaire."}
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="devices">
              <thead>
                <tr>
                  <th>Appareil</th>
                  <th>Adresse IP</th>
                  <th>MAC</th>
                  <th>Constructeur</th>
                  <th>Services</th>
                  <th>État</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((d) => (
                  <tr key={d.ip} onClick={() => setSelected(d)} className={d.kind === "robot" ? "is-robot" : ""}>
                    <td>
                      <div className="dev-cell">
                        <span className={`kind-icon ${d.kind}`}>{KIND_ICON[d.kind] ?? "·"}</span>
                        <div>
                          <strong>{d.label}</strong>
                          <span className="muted small">{d.kind_label}{d.self ? " · cet ordinateur" : ""}</span>
                        </div>
                      </div>
                    </td>
                    <td className="mono">{d.ip}</td>
                    <td className="mono small">{d.mac ?? "—"}</td>
                    <td>{d.vendor ?? <span className="muted">inconnu</span>}</td>
                    <td>
                      <div className="port-chips">
                        {d.ports.slice(0, 3).map((p) => (
                          <span key={p.port} className="port-chip" title={p.service}>
                            {p.port}
                          </span>
                        ))}
                        {d.ports.length > 3 && <span className="port-chip more">+{d.ports.length - 3}</span>}
                        {d.ports.length === 0 && <span className="muted small">—</span>}
                      </div>
                    </td>
                    <td>
                      <span className="online-state"><span className="micro-dot" />actif</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Glass>

      <div className="grid-2">
        <Glass>
          <SectionTitle title="Options de découverte" />
          <Switch
            checked={onlineVendor}
            onChange={onToggleOnline}
            label="Résolution constructeur en ligne"
            hint="Envoie uniquement les 3 premiers octets de la MAC (OUI) à maclookup.app. Désactivé par défaut."
          />
          <p className="muted small note">
            Aucune requête n'est faite vers l'extérieur pour l'analyse réseau elle-même :
            ARP, mDNS, SSDP et tests de ports restent strictement locaux.
          </p>
        </Glass>
        <Glass>
          <SectionTitle title="Méthode" />
          <ul className="method">
            <li><strong>ARP</strong> — un datagramme UDP par hôte, puis lecture du cache système.</li>
            <li><strong>mDNS</strong> — requêtes PTR sur les services connus (_irobot, _amzn-alexa, _hap…).</li>
            <li><strong>SSDP</strong> — M-SEARCH standard, puis lecture du descripteur UPnP.</li>
            <li><strong>Ports</strong> — connexion TCP simple sur 15 ports, sans payload applicatif.</li>
            <li><strong>TLS</strong> — lecture du certificat présenté (aucune authentification).</li>
          </ul>
        </Glass>
      </div>

      <Modal open={selected !== null} title={selected?.label ?? ""} onClose={() => setSelected(null)}>
        {selected && <DeviceDetail device={selected} />}
      </Modal>
    </div>
  );
}

function DeviceDetail({ device }: { device: Device }) {
  return (
    <div className="detail">
      <div className="detail-head">
        <span className={`kind-icon big ${device.kind}`}>{KIND_ICON[device.kind] ?? "·"}</span>
        <div>
          <strong>{device.kind_label}</strong>
          <p className="muted small">
            {device.ip}
            {device.mac ? ` · ${device.mac}` : ""}
          </p>
        </div>
        {device.tls?.common_name && <Pill tone="ok">certificat iRobot</Pill>}
      </div>

      <div className="kv-grid tight">
        <div><span>Constructeur</span><strong>{device.vendor ?? "inconnu"}</strong></div>
        <div><span>Nom réseau</span><strong>{device.hostname ?? "—"}</strong></div>
        <div><span>Confiance</span><strong>{device.confidence ?? "—"}</strong></div>
        <div><span>MAC aléatoire</span><strong>{device.locally_administered ? "oui" : "non"}</strong></div>
      </div>

      {device.evidence.length > 0 && (
        <>
          <h4>Indices de détection</h4>
          <ul className="evidence">
            {device.evidence.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </>
      )}

      {device.ports.length > 0 && (
        <>
          <h4>Ports ouverts</h4>
          <div className="port-list">
            {device.ports.map((p) => (
              <div key={p.port} className="port-row">
                <span className="mono">{p.port}</span>
                <span>{p.service}</span>
                <Pill tone="ok">ouvert</Pill>
              </div>
            ))}
          </div>
        </>
      )}

      {device.tls && (
        <>
          <h4>Identité TLS</h4>
          <div className="tls-box">
            {device.tls.error ? (
              <p className="muted small">Lecture impossible ({device.tls.error})</p>
            ) : (
              <>
                <div><span>Sujet</span><strong className="mono small">{device.tls.common_name}</strong></div>
                <div><span>Organisation</span><strong>{device.tls.organization}</strong></div>
                <div><span>Émetteur</span><strong>{device.tls.issuer_cn}</strong></div>
                <div><span>Version</span><strong>{device.tls.tls} · {device.tls.cipher}</strong></div>
                <div><span>Validité</span><strong>jusqu'au {device.tls.not_after}</strong></div>
              </>
            )}
          </div>
        </>
      )}

      {device.mdns && device.mdns.services.length > 0 && (
        <>
          <h4>Services mDNS</h4>
          <div className="svc-list">
            {device.mdns.services.map((s) => (
              <div key={s.service + s.instance} className="svc">
                <div>
                  <strong>{s.instance}</strong>
                  <span className="muted small">{s.service}{s.port ? ` · port ${s.port}` : ""}</span>
                </div>
                {s.txt && Object.keys(s.txt).length > 0 && (
                  <div className="txt">
                    {Object.entries(s.txt).slice(0, 8).map(([k, v]) => (
                      <span key={k}><em>{k}</em>={v}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {device.ssdp?.device && (
        <>
          <h4>Descripteur UPnP</h4>
          <div className="tls-box">
            {Object.entries(device.ssdp.device).map(([k, v]) => (
              <div key={k}><span>{k}</span><strong>{v}</strong></div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
