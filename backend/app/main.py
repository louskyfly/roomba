"""API FastAPI de ROO-LAB."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, scheduler, secret_store
from .config import APP_NAME, APP_VERSION, COMMANDS, FRONTEND_DIST, HOST, PORT, ensure_dirs
from .discovery import scan as run_scan
from .discovery.network import get_interfaces
from .roomba import service
from .ws import hub

_scan_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    db.init()
    db.add_event("info", "system", "ROO-LAB démarré")
    service.attach(hub.broadcast)
    scheduler_task = asyncio.create_task(scheduler.run(hub.broadcast))
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        service.disconnect()


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------- modèles

class Credentials(BaseModel):
    blid: str = Field(min_length=4, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    host: str = Field(min_length=7, max_length=45)


class CloudCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)
    host: str | None = None


class Command(BaseModel):
    command: str
    confirm: bool = False


class Preferences(BaseModel):
    prefs: dict[str, Any]


class Settings(BaseModel):
    online_vendor_lookup: bool | None = None


class Schedule(BaseModel):
    name: str = Field(min_length=1, max_length=59)
    days: list[int] = Field(min_length=1, max_length=7)
    at_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    command: str = "start"
    enabled: bool = True


class Confirmation(BaseModel):
    confirm: bool = False


class SchedulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=59)
    days: list[int] | None = Field(default=None, min_length=1, max_length=7)
    at_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    command: str | None = None
    enabled: bool | None = None


# --------------------------------------------------------------------- santé

@app.get("/api/health")
async def health() -> dict:
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "time": time.time(),
        "robot": {
            "configured": secret_store.has_credentials(),
            "connected": bool(service.link and service.link.status == "online"),
        },
    }


@app.get("/api/interfaces")
async def interfaces() -> dict:
    return {"interfaces": [i.to_dict() for i in get_interfaces()]}


# ------------------------------------------------------------------- réseau

@app.get("/api/network")
async def network_state() -> dict:
    last = db.last_scan()
    return {
        "interfaces": [i.to_dict() for i in get_interfaces()],
        "devices": db.list_devices(),
        "last_scan": last,
        "online_vendor_lookup": db.get_setting("online_vendor_lookup", False),
    }


@app.post("/api/network/scan")
async def network_scan(online: bool | None = None) -> dict:
    if _scan_lock.locked():
        raise HTTPException(409, "Une analyse est déjà en cours")
    async with _scan_lock:
        allow_online = (
            db.get_setting("online_vendor_lookup", False) if online is None else online
        )

        def emit(step: str, pct: int, message: str) -> None:
            hub.broadcast({"type": "scan_progress", "step": step,
                           "percent": pct, "message": message})

        try:
            report = await run_scan(emit=emit, allow_online_vendor=allow_online)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        hub.broadcast({"type": "scan_done", "report": report})
        return report


@app.get("/api/network/last")
async def network_last() -> dict:
    last = db.last_scan()
    if not last:
        raise HTTPException(404, "Aucune analyse enregistrée")
    return last


# --------------------------------------------------------------------- robot

@app.get("/api/robot")
async def robot_state() -> dict:
    return {
        "snapshot": service.snapshot(),
        "commands": COMMANDS,
        "has_credentials": secret_store.has_credentials(),
        "ip_hint": service.robot_ip_hint(),
    }


@app.post("/api/robot/credentials")
async def save_credentials(creds: Credentials) -> dict:
    if not secret_store.has_credentials():
        db.add_event("info", "robot", "Enregistrement des identifiants locaux")
    service.save_credentials(creds.blid, creds.password, creds.host)
    if service.link:
        return {"ok": True, "snapshot": await service.connect()}
    return {"ok": True, "snapshot": service.snapshot()}


@app.delete("/api/robot/credentials")
async def delete_credentials() -> dict:
    service.clear_credentials()
    db.add_event("warning", "robot", "Identifiants locaux supprimés")
    return {"ok": True}


@app.post("/api/robot/cloud-retrieve")
async def cloud_retrieve(payload: CloudCredentials) -> dict:
    """Récupération ponctuelle des identifiants locaux via le compte iRobot.

    Les identifiants de compte ne sont ni journalisés ni stockés. En cas de
    succès, la paire BLID/mot de passe du robot ciblé est enregistrée localement
    (chiffrée DPAPI) comme pour une saisie manuelle.
    """
    from .roomba import cloud as cloud_mod

    result = await asyncio.to_thread(cloud_mod.retrieve, payload.email, payload.password)
    robots = result.get("robots") or []
    if not robots:
        return {
            "ok": False,
            "robots": [],
            "error": result.get("error"),
            "detail": result.get("detail") or "Aucun robot trouvé.",
        }

    # Choisir le robot : préférence SKU j7 ou correspondance BLID/certificat connu.
    chosen = robots[0]
    hint_ip = payload.host or service.robot_ip_hint() or ""
    for r in robots:
        sku = str(r.get("sku") or "").lower()
        if "j7" in sku or "j755" in sku:
            chosen = r
            break

    host = hint_ip or ""
    if host:
        service.save_credentials(chosen["blid"], chosen["password"], host)
        db.add_event("info", "robot", "Identifiants récupérés via le compte iRobot (chiffrés)")
        snap = await service.connect()
        return {
            "ok": True,
            "saved": True,
            "blid": chosen["blid"],
            "robot_name": chosen.get("name"),
            "robots_found": len(robots),
            "snapshot": snap,
        }

    # Pas d'IP connue : on retourne le BLID/mot de passe pour saisie/confirmation côté UI
    # (le mot de passe n'est pas stocké côté serveur tant que l'hôte n'est pas fourni).
    return {
        "ok": True,
        "saved": False,
        "blid": chosen["blid"],
        "password": chosen["password"],
        "robot_name": chosen.get("name"),
        "robots_found": len(robots),
        "detail": "Identifiants récupérés ; renseignez l'adresse IP du robot pour enregistrer.",
    }


@app.post("/api/robot/connect")
async def robot_connect() -> dict:
    return {"ok": True, "snapshot": await service.connect()}


@app.post("/api/robot/disconnect")
async def robot_disconnect() -> dict:
    service.disconnect()
    return {"ok": True}


@app.post("/api/robot/command")
async def robot_command(payload: Command) -> dict:
    try:
        result = service.command(payload.command, payload.confirm)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return result


@app.post("/api/robot/preferences")
async def robot_preferences(payload: Preferences) -> dict:
    if not service.link or service.link.status != "online":
        raise HTTPException(409, "Robot non connecté")
    ok = service.link.set_preferences(payload.prefs)
    db.add_event("info", "command", "Préférences modifiées", payload.prefs)
    return {"ok": ok}


# ---------------------------------------------------------------- historiques

@app.get("/api/missions")
async def missions(limit: int = 25) -> dict:
    return {"missions": db.list_missions(limit)}


@app.get("/api/events")
async def events(limit: int = 100) -> dict:
    return {"events": db.list_events(limit)}


@app.get("/api/telemetry")
async def telemetry(minutes: int = 60, limit: int = 5000) -> dict:
    since = time.time() - max(1, min(minutes, 60 * 24 * 7)) * 60
    return {"samples": db.telemetry_since(since, limit)}


@app.get("/api/stats")
async def stats() -> dict:
    rows = db.query(
        """SELECT COUNT(*) AS missions,
                  COALESCE(SUM(duration_s), 0) AS seconds,
                  COALESCE(SUM(area_sqft), 0) AS sqft,
                  COALESCE(AVG(duration_s), 0) AS avg_seconds
           FROM missions WHERE ended_at IS NOT NULL"""
    )
    return rows[0] if rows else {}


# -------------------------------------------------------------- planifications

def _validate_schedule(days: list[int] | None, command: str | None) -> None:
    if days is not None and any(d < 0 or d > 6 for d in days):
        raise HTTPException(400, "Jours invalides (0 = lundi … 6 = dimanche)")
    if command is not None and command not in COMMANDS:
        raise HTTPException(400, "Commande invalide")


@app.get("/api/schedules")
async def schedules() -> dict:
    return {
        "schedules": db.list_schedules(),
        "next": _next_runs(),
    }


def _next_runs() -> dict[int, float]:
    """Prochaine occurrence de chaque passage, en timestamp local."""
    from datetime import datetime, timedelta

    now = datetime.now()
    out: dict[int, float] = {}
    for schedule in db.list_schedules():
        if not schedule.get("enabled"):
            continue
        try:
            hour, minute = (int(p) for p in schedule["at_time"].split(":"))
        except (ValueError, KeyError):
            continue
        for offset in range(0, 8):
            day = now + timedelta(days=offset)
            if day.weekday() not in (schedule.get("days") or []):
                continue
            moment = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if moment <= now:
                continue
            out[schedule["id"]] = moment.timestamp()
            break
    return out


@app.post("/api/schedules")
async def create_schedule(payload: Schedule) -> dict:
    _validate_schedule(payload.days, payload.command)
    row = db.create_schedule(
        payload.name.strip(), payload.days, payload.at_time,
        payload.command, payload.enabled,
    )
    db.add_event("info", "schedule", f"Passage programmé « {row.get('name')} »")
    hub.broadcast({"type": "schedules_changed"})
    return {"schedule": row, "next": _next_runs()}


@app.patch("/api/schedules/{schedule_id}")
async def patch_schedule(schedule_id: int, payload: SchedulePatch) -> dict:
    if db.get_schedule(schedule_id) is None:
        raise HTTPException(404, "Passage introuvable")
    _validate_schedule(payload.days, payload.command)
    row = db.update_schedule(schedule_id, payload.model_dump(exclude_none=True))
    db.add_event("info", "schedule", f"Passage « {row.get('name')} » modifié")
    hub.broadcast({"type": "schedules_changed"})
    return {"schedule": row, "next": _next_runs()}


@app.delete("/api/schedules/{schedule_id}")
async def remove_schedule(schedule_id: int) -> dict:
    if not db.delete_schedule(schedule_id):
        raise HTTPException(404, "Passage introuvable")
    db.add_event("info", "schedule", "Passage programmé supprimé")
    hub.broadcast({"type": "schedules_changed"})
    return {"ok": True}


@app.post("/api/schedules/{schedule_id}/run")
async def run_schedule(schedule_id: int, payload: Confirmation) -> dict:
    row = db.get_schedule(schedule_id)
    if row is None:
        raise HTTPException(404, "Passage introuvable")
    if not payload.confirm:
        raise HTTPException(403, "Confirmation explicite requise")
    try:
        result = service.command(row.get("command") or "start", confirm=True)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.mark_schedule_run(schedule_id, "envoyé (manuel)")
    db.add_event("info", "schedule", f"Passage « {row.get('name')} » lancé manuellement")
    return {"ok": bool(result.get("ok")), "schedule": db.get_schedule(schedule_id)}


# ------------------------------------------------------------------- réglages

@app.get("/api/settings")
async def get_settings() -> dict:
    return {
        "online_vendor_lookup": db.get_setting("online_vendor_lookup", False),
    }


@app.post("/api/settings")
async def post_settings(payload: Settings) -> dict:
    if payload.online_vendor_lookup is not None:
        db.set_setting("online_vendor_lookup", payload.online_vendor_lookup)
    return await get_settings()


# ------------------------------------------------------------------ websocket

@app.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        await ws.send_json({
            "type": "hello",
            "robot": service.snapshot(),
            "scan": db.last_scan(),
        })
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.disconnect(ws)


# ------------------------------------------------------------------ frontend

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")


def main() -> None:
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
