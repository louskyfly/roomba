"""Client MQTT/TLS local du Roomba (protocole v3, port 8883).

Le robot expose un broker MQTT propre sur le LAN. L'authentification est une paire
BLID / mot de passe local fournie par iRobot ; elle transite dans le tunnel TLS.
Aucun certificat client n'est nécessaire, aucun contournement n'est effectué.

Référence : dorita980 (koalazak), testé sur les séries 900 / e / i / j.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import threading
import time
from typing import Any, Callable

import paho.mqtt.client as mqtt

SNAPSHOT_FIELDS = [
    "name", "sku", "softwareVer", "batteryType", "batPct", "bin", "dock",
    "cleanMissionStatus", "cleanSchedule", "signal", "pose", "lastCommand",
    "cap", "pmaps", "wifistat", "netinfo", "wlcfg", "tz", "langs", "country",
    "bbchg3", "bbrun", "bbsys", "bbmssn", "cloudEnv",
]

# Cycles/phase iRobot → libellé interne (aucune interprétation au-delà du documenté).
CYCLE_LABELS = {
    "none": "repos",
    "clean": "nettoyage",
    "quick": "nettoyage rapide",
    "spot": "nettoyage localisé",
    "evac": "vidage du bac",
    "dock": "retour station",
    "train": "apprentissage",
}


def derive_status(mission: dict | None, dock: dict | None, bin_state: dict | None) -> str:
    if not mission:
        return "unknown"
    cycle = mission.get("cycle") or "none"
    phase = mission.get("phase") or ""
    error = mission.get("error") or 0
    if error:
        return "error"
    if phase in ("charge",) and cycle == "none":
        return "docked" if (dock or {}).get("known") else "charging"
    if phase == "run":
        if cycle == "evac":
            return "emptying"
        return "cleaning"
    if phase == "pause":
        return "paused"
    if phase in ("hmUsrDock", "hmPostMsn", "hmMidMsn"):
        return "returning"
    if phase in ("stop", "stuck"):
        return "stopped"
    if cycle == "none" and (bin_state or {}).get("full"):
        return "bin_full"
    return "idle"


class RoombaLink:
    """Connexion locale persistante, exécutée dans un thread dédié."""

    def __init__(
        self,
        host: str,
        blid: str,
        password: str,
        on_state: Callable[[dict], None] | None = None,
        on_status: Callable[[str, str | None], None] | None = None,
    ):
        self.host = host
        self.blid = blid
        self._password = password
        self._on_state = on_state
        self._on_status = on_status
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: mqtt.Client | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {}
        self.status = "idle"
        self.last_error: str | None = None
        self.connected_at: float | None = None
        self.messages = 0

    # ------------------------------------------------------------ cycle de vie
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._loop = loop
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="roomba-mqtt", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        client = self._client
        if client is not None:
            try:
                client.disconnect()
                client.loop_stop()
            except Exception:
                pass
        self._set_status("offline", None)

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ---------------------------------------------------------------- interne
    def _emit(self, fn, *args) -> None:
        if fn and self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(fn, *args)

    def _set_status(self, status: str, detail: str | None) -> None:
        self.status = status
        if detail:
            self.last_error = detail
        self._emit(self._on_status, status, detail)

    def _merge(self, payload: dict) -> None:
        with self._lock:
            reported = ((payload or {}).get("state") or {}).get("reported") or {}
            if not reported:
                return
            self.state.update(reported)
            self.messages += 1
            snapshot = self.snapshot()
        self._emit(self._on_state, snapshot)

    def snapshot(self) -> dict:
        with self._lock:
            state = dict(self.state)
        mission = state.get("cleanMissionStatus") or {}
        return {
            "connected": self.status == "online",
            "status": self.status,
            "link": {
                "host": self.host,
                "connected_at": self.connected_at,
                "messages": self.messages,
                "last_error": self.last_error,
            },
            "identity": {
                "name": state.get("name"),
                "sku": state.get("sku"),
                "software": state.get("softwareVer"),
                "battery_type": state.get("batteryType"),
                "country": state.get("country"),
            },
            "battery": state.get("batPct"),
            "bin": state.get("bin"),
            "dock": state.get("dock"),
            "mission": mission or None,
            "mission_label": CYCLE_LABELS.get(mission.get("cycle") or "", None),
            "status_label": derive_status(mission, state.get("dock"), state.get("bin")),
            "schedule": state.get("cleanSchedule"),
            "signal": state.get("signal"),
            "pose": state.get("pose"),
            "map": _map_meta(state),
            "last_command": state.get("lastCommand"),
            "capabilities": state.get("cap"),
            "network": {
                "wifi": state.get("wifistat"),
                "ip": state.get("netinfo", {}).get("addr") if state.get("netinfo") else None,
            },
            "counters": {
                "bbrun": state.get("bbrun"),
                "bbchg3": state.get("bbchg3"),
                "bbmssn": state.get("bbmssn"),
            },
            "updated_at": time.time() if state else None,
        }

    # ------------------------------------------------------------------- MQTT
    def _run(self) -> None:
        self._set_status("connecting", None)
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.blid,
            protocol=mqtt.MQTTv311,
            clean_session=False,
        )
        client.username_pw_set(self.blid, self._password)
        client.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        client.tls_insecure_set(True)
        client.reconnect_delay_set(min_delay=2, max_delay=30)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self._client = client

        while not self._stop.is_set():
            try:
                client.connect(self.host, 8883, keepalive=30)
                client.loop_forever(retry_first_connection=False)
            except Exception as exc:
                if self._stop.is_set():
                    break
                self._set_status("offline", f"{type(exc).__name__}: {exc}")
                time.sleep(3)
            if not self._stop.is_set():
                self._set_status("reconnecting", None)
                time.sleep(2)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if getattr(reason_code, "is_failure", False):
            detail = f"CONNACK {getattr(reason_code, 'value', reason_code)}"
            if "not authorized" in str(reason_code).lower() or getattr(reason_code, "value", 0) == 5:
                detail = "Identifiants refusés par le robot (BLID / mot de passe)"
            self._set_status("auth_error", detail)
            return
        self.connected_at = time.time()
        self._set_status("online", None)
        # abonnement défensif : le robot publie normalement sans souscription
        try:
            client.subscribe("#")
        except Exception:
            pass

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if self._stop.is_set():
            self._set_status("offline", None)
        else:
            self._set_status("reconnecting", f"Déconnexion ({reason_code})")

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8", "replace"))
        except (ValueError, UnicodeDecodeError):
            return
        if isinstance(payload, dict):
            self._merge(payload)

    # -------------------------------------------------------------- commandes
    def command(self, name: str, args: dict | None = None) -> bool:
        client = self._client
        if client is None or self.status != "online":
            return False
        body = {
            "command": name,
            "time": int(time.time()),
            "initiator": "localApp",
        }
        if args:
            body.update(args)
        result = client.publish("cmd", json.dumps(body))
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def set_preferences(self, prefs: dict) -> bool:
        client = self._client
        if client is None or self.status != "online":
            return False
        body = {"state": prefs}
        result = client.publish("delta", json.dumps(body))
        return result.rc == mqtt.MQTT_ERR_SUCCESS


def _map_meta(state: dict) -> dict | None:
    """Métadonnées de carte exposées par le robot, sans jamais inventer de plan."""
    pmaps = state.get("pmaps")
    if not pmaps:
        return None
    maps = []
    for pmap_id, value in (pmaps.items() if isinstance(pmaps, dict) else []):
        entry = value if isinstance(value, dict) else {}
        maps.append({
            "id": pmap_id,
            "version": entry.get("user_pmapv_id") or entry.get("pmapv_id"),
            "rooms": [
                {"id": r.get("region_id"), "name": r.get("region_name"),
                 "type": r.get("region_type")}
                for r in (entry.get("regions") or [])
            ] if isinstance(entry.get("regions"), list) else [],
        })
    return {"maps": maps} if maps else None
