"""Planificateur local : déclenche les nettoyages programmés.

Le robot ne reçoit une commande que s'il est connecté au broker local.
Sinon le passage est marqué « ignoré » dans l'historique, sans réessai.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Callable

from . import db
from .roomba import service

TICK_SECONDS = 20
# Fenêtre pendant laquelle un passage programmé reste valide (secondes).
GRACE_SECONDS = 120

Broadcast = Callable[[dict], None]


def _scheduled_moment(now: datetime, at_time: str) -> datetime:
    hour, minute = (int(part) for part in at_time.split(":"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _run(schedule: dict, broadcast: Broadcast | None) -> None:
    name = schedule.get("name") or "Passage"
    command = schedule.get("command") or "start"
    now = time.time()

    if not service.link or service.link.status != "online":
        db.mark_schedule_run(schedule["id"], "ignoré — robot hors ligne")
        db.add_event(
            "warning",
            "schedule",
            f"Passage « {name} » ignoré : robot hors ligne",
            {"schedule_id": schedule["id"]},
        )
        result = {"ok": False, "reason": "offline"}
    else:
        try:
            service.command(command, confirm=True)
            db.mark_schedule_run(schedule["id"], "envoyé")
            result = {"ok": True}
        except (PermissionError, RuntimeError, ValueError) as exc:
            db.mark_schedule_run(schedule["id"], f"échec — {exc}")
            db.add_event(
                "error",
                "schedule",
                f"Passage « {name} » en échec : {exc}",
                {"schedule_id": schedule["id"]},
            )
            result = {"ok": False, "reason": str(exc)}

    if broadcast:
        broadcast({
            "type": "schedule_run",
            "schedule_id": schedule["id"],
            "name": name,
            "result": result,
            "at": now,
        })


def tick(now: datetime | None = None, broadcast: Broadcast | None = None) -> int:
    """Exécute les passages dus. Retourne le nombre de passages traités."""
    now = now or datetime.now()
    handled = 0
    for schedule in db.list_schedules():
        if not schedule.get("enabled"):
            continue
        days = schedule.get("days") or []
        if now.weekday() not in days:
            continue
        try:
            moment = _scheduled_moment(now, schedule["at_time"])
        except (ValueError, AttributeError):
            continue
        delta = (now - moment).total_seconds()
        if not (0 <= delta < GRACE_SECONDS):
            continue
        last_run = schedule.get("last_run_at")
        if last_run and last_run >= moment.timestamp():
            continue
        _run(schedule, broadcast)
        handled += 1
    return handled


async def run(broadcast: Broadcast | None = None) -> None:
    """Boucle de fond : vérifie les passages toutes les 20 secondes."""
    while True:
        try:
            tick(broadcast=broadcast)
        except Exception as exc:  # noqa: BLE001 - la boucle ne doit jamais mourir
            db.add_event("error", "scheduler", f"Planificateur : {exc}")
        await asyncio.sleep(TICK_SECONDS)
