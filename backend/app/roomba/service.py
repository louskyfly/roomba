"""Service robot : cycle de vie de la connexion, persistance, diffusion temps réel."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from .. import db, secret_store
from ..config import COMMANDS
from .link import RoombaLink

Broadcast = Callable[[dict], None]


class RobotService:
    def __init__(self) -> None:
        self.link: RoombaLink | None = None
        self._broadcast: Broadcast | None = None
        self._snapshot: dict[str, Any] = self._empty_snapshot()
        self._last_sample = 0.0
        self._mission_id: int | None = None
        self._last_error: int = 0
        self._last_cycle: str | None = None

    # ------------------------------------------------------------------ setup
    def attach(self, broadcast: Broadcast) -> None:
        self._broadcast = broadcast
        if secret_store.has_credentials():
            asyncio.get_event_loop().create_task(self.connect(auto=True))

    def _empty_snapshot(self) -> dict[str, Any]:
        return {
            "configured": secret_store.has_credentials(),
            "connected": False,
            "status": "unconfigured",
            "link": None,
            "identity": {},
            "battery": None,
            "mission": None,
            "pose": None,
            "map": None,
            "updated_at": None,
        }

    def _emit(self) -> None:
        if self._broadcast:
            self._broadcast({"type": "robot", "snapshot": self._snapshot})

    # ------------------------------------------------------------- connexion
    def robot_ip_hint(self) -> str | None:
        creds = secret_store.load_credentials() or {}
        if creds.get("host"):
            return creds["host"]
        scan = db.last_scan()
        if scan and scan.get("report"):
            robot = scan["report"].get("robot")
            if robot:
                return robot.get("ip")
        return None

    async def connect(self, auto: bool = False) -> dict[str, Any]:
        creds = secret_store.load_credentials()
        if not creds:
            self._snapshot = {**self._empty_snapshot(), "status": "unconfigured"}
            self._emit()
            return self._snapshot

        host = creds.get("host") or self.robot_ip_hint()
        if not host:
            self._snapshot = {
                **self._empty_snapshot(),
                "status": "no_host",
                "configured": True,
            }
            self._emit()
            return self._snapshot

        if self.link:
            self.link.stop()
            self.link = None

        loop = asyncio.get_running_loop()
        self.link = RoombaLink(
            host=host,
            blid=creds["blid"],
            password=creds["password"],
            on_state=self._on_state,
            on_status=self._on_status,
        )
        self.link.start(loop)
        if not self._snapshot.get("connected"):
            self._snapshot = {**self._empty_snapshot(), "configured": True,
                              "status": "connecting"}
            self._emit()
        return self._snapshot

    def disconnect(self) -> None:
        if self.link:
            self.link.stop()
            self.link = None
        self._snapshot = {**self._snapshot, "connected": False, "status": "offline"}
        self._emit()

    def save_credentials(self, blid: str, password: str, host: str) -> None:
        secret_store.save_credentials(blid.strip(), password.strip(), host.strip())
        db.add_event("info", "robot", "Identifiants locaux enregistrés (chiffrés)")
        self._snapshot = {**self._empty_snapshot(), "configured": True}
        self._emit()

    def clear_credentials(self) -> None:
        self.disconnect()
        secret_store.clear_credentials()
        self._snapshot = self._empty_snapshot()
        self._emit()

    # --------------------------------------------------------------- callbacks
    def _on_status(self, status: str, detail: str | None) -> None:
        self._snapshot = {**self._snapshot, "connected": status == "online",
                          "status": status}
        if detail:
            self._snapshot["link"] = {**(self._snapshot.get("link") or {}),
                                      "last_error": detail}
        if status == "auth_error":
            db.add_event("error", "robot", detail or "Authentification refusée")
        self._emit()

    def _on_state(self, snap: dict[str, Any]) -> None:
        snap["configured"] = True
        self._snapshot = snap
        self._emit()
        self._track(snap)

    # -------------------------------------------------------------- persistance
    def _track(self, snap: dict[str, Any]) -> None:
        mission = snap.get("mission") or {}
        now = time.time()
        battery = snap.get("battery")
        pose = snap.get("pose") or {}
        point = pose.get("point") or {}
        cycle = mission.get("cycle")

        if now - self._last_sample >= 4:
            self._last_sample = now
            db.add_telemetry(
                ts=now, battery=battery, phase=mission.get("phase"),
                cycle=cycle, error=mission.get("error") or 0,
                x=point.get("x"), y=point.get("y"), theta=pose.get("theta"),
                mission_id=self._mission_id,
            )

        if cycle == "clean" and self._last_cycle != "clean":
            self._mission_id = db.start_mission(mission.get("nMssn"), battery)
            db.add_event("info", "mission", "Début de nettoyage",
                         {"mission": mission.get("nMssn")})
        elif cycle != "clean" and self._last_cycle == "clean" and self._mission_id:
            started = None
            rows = db.query("SELECT started_at, battery_start FROM missions WHERE id=?",
                            (self._mission_id,))
            if rows:
                started = rows[0]["started_at"]
            db.finish_mission(
                self._mission_id,
                duration_s=int(now - started) if started else None,
                area_sqft=mission.get("sqft"),
                battery_end=battery,
            )
            db.add_event("info", "mission", "Fin de nettoyage",
                         {"area_sqft": mission.get("sqft")})
            self._mission_id = None
        if cycle:
            self._last_cycle = cycle

        error = mission.get("error") or 0
        if error and error != self._last_error:
            db.add_event("error", "robot", f"Erreur robot {error}", {"code": error})
        self._last_error = error

        bin_state = snap.get("bin") or {}
        if bin_state.get("full"):
            with_full = db.get_setting("bin_full_notified", False)
            if not with_full:
                db.add_event("warning", "robot", "Bac plein : intervention requise")
                db.set_setting("bin_full_notified", True)
        elif bin_state.get("present") and not bin_state.get("full"):
            db.set_setting("bin_full_notified", False)

    # -------------------------------------------------------------- commandes
    def command(self, name: str, confirm: bool = False, args: dict | None = None) -> dict:
        if name not in COMMANDS:
            raise ValueError("Commande inconnue")
        meta = COMMANDS[name]
        if meta.get("risky") and not confirm:
            raise PermissionError(
                "Confirmation explicite requise pour cette commande"
            )
        if not self.link or self.link.status != "online":
            raise RuntimeError("Robot non connecté")
        ok = self.link.command(name, args)
        db.add_event(
            "info" if ok else "error",
            "command",
            f"Commande « {meta['label']} » {'envoyée' if ok else 'échouée'}",
            {"command": name},
        )
        return {"ok": ok, "command": name}

    def snapshot(self) -> dict[str, Any]:
        snap = dict(self._snapshot)
        snap["configured"] = secret_store.has_credentials()
        snap["ip_hint"] = self.robot_ip_hint()
        return snap


service = RobotService()
