import { useEffect, useState } from "react";
import type { RobotSnapshot, ScanReport } from "../types";
import { Button, Glass, Modal, Pill, SectionTitle, Switch } from "../components/ui";
import { statusText } from "../lib/format";
import { api, ApiError } from "../lib/api";

export function Settings({
  snapshot,
  scan,
  busy,
  onlineVendor,
  ipHint,
  onSave,
  onClear,
  onConnect,
  onDisconnect,
  onToggleOnline,
}: {
  snapshot: RobotSnapshot | null;
  scan: ScanReport | null;
  busy: boolean;
  onlineVendor: boolean;
  ipHint: string;
  onSave: (blid: string, password: string, host: string) => void;
  onClear: () => void;
  onConnect: () => void;
  onDisconnect: () => void;
  onToggleOnline: (v: boolean) => void;
}) {
  const [blid, setBlid] = useState("");
  const [password, setPassword] = useState("");
  const [host, setHost] = useState(ipHint);
  const [reveal, setReveal] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [cloudEmail, setCloudEmail] = useState("");
  const [cloudPass, setCloudPass] = useState("");
  const [cloudReveal, setCloudReveal] = useState(false);
  const [cloudBusy, setCloudBusy] = useState(false);
  const [cloudMsg, setCloudMsg] = useState<{ tone: "ok" | "error" | "info"; text: string } | null>(null);

  useEffect(() => {
    if (ipHint && !host) setHost(ipHint);
  }, [ipHint, host]);

  const configured = snapshot?.configured ?? false;
  const connected = snapshot?.connected ?? false;
  const detected = scan?.robot;
  const cn = detected?.tls?.common_name ?? "";

  const retrieveCloud = async () => {
    setCloudMsg(null);
    setCloudBusy(true);
    try {
      const targetHost = host.trim() || ipHint || "";
      const res = await api.cloudRetrieve(cloudEmail.trim(), cloudPass, targetHost || undefined);
      if (!res.ok) {
        setCloudMsg({
          tone: "error",
          text: res.detail || "Récupération impossible. Vérifiez vos identifiants ou utilisez la saisie manuelle.",
        });
        return;
      }
      if (res.saved && res.blid) {
        setBlid(res.blid);
        setPassword("");
        setCloudMsg({
          tone: "ok",
          text: `Identifiants récupérés${res.robot_name ? ` pour « ${res.robot_name} »` : ""} et enregistrés. Connexion en cours…`,
        });
        // rafraîchissement via connexion déjà lancée côté serveur
        window.setTimeout(() => window.location.reload(), 1200);
      } else if (res.blid && res.password) {
        setBlid(res.blid);
        setPassword(res.password);
        if (!host && ipHint) setHost(ipHint);
        setCloudMsg({
          tone: "info",
          text:
            res.detail ||
            "Identifiants récupérés. Vérifiez l'adresse IP puis cliquez sur « Enregistrer et connecter ».",
        });
      }
    } catch (err) {
      setCloudMsg({
        tone: "error",
        text: err instanceof ApiError ? err.message : "Échec de la récupération cloud.",
      });
    } finally {
      setCloudBusy(false);
      setCloudPass("");
    }
  };

  return (
    <div className="stack">
      <Glass className="settings-status">
        <div>
          <span className="eyebrow">Appairage local</span>
          <h2>{configured ? "Identifiants enregistrés" : "Aucun identifiant"}</h2>
          <p className="muted">
            État de la liaison : <strong>{statusText(snapshot?.status)}</strong>
            {snapshot?.link?.host ? ` · ${snapshot.link.host}` : ""}
          </p>
        </div>
        <div className="settings-actions">
          <Pill tone={configured ? "ok" : "warn"} dot>
            {configured ? "chiffré sur ce PC" : "requis pour contrôler"}
          </Pill>
          {configured && (
            connected ? (
              <Button variant="ghost" onClick={onDisconnect} disabled={busy}>
                Déconnecter
              </Button>
            ) : (
              <Button variant="glass" onClick={onConnect} disabled={busy}>
                Se connecter
              </Button>
            )
          )}
        </div>
      </Glass>

      <div className="grid-2">
        <Glass>
          <SectionTitle title="Identifiants locaux du robot (BLID / mot de passe)" />
          <p className="muted small">
            <strong>Ce ne sont pas</strong> vos identifiants de compte iRobot (e-mail/mot de passe
            de l’app iRobot Home). Ce sont les identifiants <em>locaux</em> du robot : le BLID est
            un identifiant long (souvent proche de <code>{cn ? cn.replace("iRobot-", "") : "5F0726…"}</code>)
            et le mot de passe local commence généralement par <code>:1:</code>. Si vous ne les
            avez pas, utilisez le bloc « Récupération automatique » ci-dessous.
          </p>
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!blid.trim() || !password.trim() || !host.trim()) return;
              onSave(blid.trim(), password.trim(), host.trim());
            }}
          >
            <label className="field">
              <span>BLID (identifiant robot)</span>
              <input
                value={blid}
                onChange={(e) => setBlid(e.target.value)}
                placeholder={cn ? cn.replace("iRobot-", "") : "ex. 5F0726EEE8BE4917…"}
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            <label className="field">
              <span>Mot de passe local</span>
              <div className="input-row">
                <input
                  type={reveal ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder=":1:1742…:…"
                  autoComplete="off"
                  spellCheck={false}
                />
                <button type="button" className="icon-btn" onClick={() => setReveal((v) => !v)}>
                  {reveal ? "masquer" : "voir"}
                </button>
              </div>
            </label>
            <label className="field">
              <span>Adresse IP du robot</span>
              <input
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="192.168.1.104"
                inputMode="numeric"
              />
            </label>
            <div className="form-actions">
              <Button type="submit" variant="primary" disabled={busy}>
                {configured ? "Remplacer et reconnecter" : "Enregistrer et connecter"}
              </Button>
              {snapshot?.ip_hint && (
                <Button variant="ghost" onClick={() => setHost(snapshot.ip_hint ?? "")}>
                  Utiliser {snapshot.ip_hint}
                </Button>
              )}
            </div>
          </form>

          <div className="cloud-box">
            <SectionTitle title="Récupération automatique (compte iRobot)" />
            <p className="muted small">
              <strong>C’est ici</strong> qu’il faut saisir l’e-mail et le mot de passe de votre{" "}
              <strong>compte iRobot / application iRobot Home</strong> (pas le Wi-Fi). ROO-LAB les
              envoie <strong>une seule fois</strong> aux serveurs iRobot pour récupérer la paire
              locale du robot (BLID + mot de passe <code>:1:…</code>), puis les efface de la mémoire ;
              ils ne sont ni stockés ni envoyés ailleurs. L’API iRobot évolue : si cela échoue,
              utilisez la saisie manuelle ci-dessus.
            </p>
            <div className="form">
              <label className="field">
                <span>E-mail du compte iRobot</span>
                <input
                  type="email"
                  value={cloudEmail}
                  onChange={(e) => setCloudEmail(e.target.value)}
                  placeholder="vous@exemple.com"
                  autoComplete="username"
                />
              </label>
              <label className="field">
                <span>Mot de passe du compte iRobot</span>
                <div className="input-row">
                  <input
                    type={cloudReveal ? "text" : "password"}
                    value={cloudPass}
                    onChange={(e) => setCloudPass(e.target.value)}
                    placeholder="mot de passe iRobot"
                    autoComplete="current-password"
                  />
                  <button type="button" className="icon-btn" onClick={() => setCloudReveal((v) => !v)}>
                    {cloudReveal ? "masquer" : "voir"}
                  </button>
                </div>
              </label>
              <div className="form-actions">
                <Button
                  variant="glass"
                  onClick={() => void retrieveCloud()}
                  disabled={cloudBusy || busy || !cloudEmail.trim() || !cloudPass}
                >
                  {cloudBusy ? "Récupération…" : "Récupérer et connecter"}
                </Button>
              </div>
              {cloudMsg && (
                <p className={`cloud-msg ${cloudMsg.tone}`}>{cloudMsg.text}</p>
              )}
            </div>
          </div>

          <details className="help">
            <summary>Saisie manuelle / aide</summary>
            <p>
              Si la récupération automatique échoue, utilisez un outil à jour (par ex.{" "}
              <code>get-roomba-password-cloud</code> de dorita980) pour obtenir la paire BLID /
              mot de passe locale depuis votre compte iRobot, puis collez-la ci-dessus. Le BLID
              correspond souvent à la fin du nom du certificat ({cn ? cn.replace("iRobot-", "") : "5F0726…"}).
            </p>
            <p className="muted">
              Après cette étape, tout le contrôle se fait sur le LAN, sans cloud. Le mot de passe
              Wi-Fi n'est jamais demandé par ROO-LAB.
            </p>
          </details>
        </Glass>

        <div className="stack">
          <Glass>
            <SectionTitle title="Matériel" aside={<Pill tone="ok">vérifié</Pill>} />
            <div className="kv-grid tight">
              <div><span>Modèle</span><strong>iRobot Roomba j7+</strong></div>
              <div><span>SKU</span><strong className="mono">j755840</strong></div>
              <div><span>Numéro de série</span><strong className="mono small">J755840Y220328N101649</strong></div>
              <div><span>Firmware annoncé</span><strong className="mono">24.29.3</strong></div>
              <div><span>Adresse détectée</span><strong className="mono">{detected?.ip ?? "—"}</strong></div>
              <div><span>MAC</span><strong className="mono small">{detected?.mac ?? "—"}</strong></div>
              <div><span>Certificat</span><strong className="mono small">{cn || "—"}</strong></div>
              <div><span>Port local</span><strong>MQTT/TLS · 8883</strong></div>
            </div>
          </Glass>

          <Glass>
            <SectionTitle title="Découverte" />
            <Switch
              checked={onlineVendor}
              onChange={onToggleOnline}
              label="Résolution OUI en ligne"
              hint="Option secondaire : seuls les 3 premiers octets de la MAC sont envoyés. Désactivée par défaut."
            />
          </Glass>
        </div>
      </div>

      <Glass>
        <SectionTitle title="Sécurité & limites" />
        <div className="security-grid">
          <div>
            <strong>Ce que ROO-LAB ne fait pas</strong>
            <ul className="method">
              <li>Aucun firmware modifié, aucun root, aucun jailbreak.</li>
              <li>Aucun contournement d'authentification ni de mot de passe.</li>
              <li>Aucun envoi de vos identifiants ou de votre Wi-Fi à un service tiers.</li>
              <li>Aucune commande de nettoyage sans confirmation explicite.</li>
            </ul>
          </div>
          <div>
            <strong>Limites connues du j7+</strong>
            <ul className="method">
              <li>Une seule connexion locale simultanée sur le broker MQTT.</li>
              <li>Le plan de sol rendu n'est pas exposé en local.</li>
              <li>Le mot de passe local ne peut plus être lu par la méthode « bouton HOME ».</li>
              <li>Une mise à jour firmware peut modifier le protocole.</li>
              <li>
                Le certificat du robot est observé et affiché, mais pas encore épinglé :
                la liaison TLS ne vérifie pas la chaîne de certification iRobot.
              </li>
            </ul>
          </div>
        </div>
      </Glass>

      <Glass className="danger-zone">
        <SectionTitle title="Zone sensible" />
        <div className="danger-row">
          <div>
            <strong>Supprimer les identifiants locaux</strong>
            <p className="muted small">
              Efface le fichier chiffré. Aucun réglage du robot n'est modifié.
            </p>
          </div>
          <Button variant="danger" onClick={() => setConfirmClear(true)} disabled={!configured || busy}>
            Supprimer
          </Button>
        </div>
      </Glass>

      <Modal open={confirmClear} title="Supprimer les identifiants ?" onClose={() => setConfirmClear(false)}>
        <p className="modal-text">
          La connexion locale sera interrompue et il faudra ressaisir le BLID et le mot de passe.
          Cette action n'affecte ni le robot ni votre compte iRobot.
        </p>
        <div className="modal-actions">
          <Button variant="ghost" onClick={() => setConfirmClear(false)}>Annuler</Button>
          <Button
            variant="danger"
            onClick={() => {
              onClear();
              setConfirmClear(false);
            }}
          >
            Supprimer
          </Button>
        </div>
      </Modal>
    </div>
  );
}
