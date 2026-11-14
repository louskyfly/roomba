"""Accès SQLite : appareils, télémétrie, missions, événements, réglages."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .config import DB_PATH, ensure_dirs

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    ip TEXT PRIMARY KEY,
    mac TEXT,
    vendor TEXT,
    hostname TEXT,
    kind TEXT,
    label TEXT,
    services TEXT,
    evidence TEXT,
    online INTEGER DEFAULT 1,
    last_seen REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    finished_at REAL,
    subnet TEXT,
    device_count INTEGER DEFAULT 0,
    report TEXT
);

CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    battery INTEGER,
    phase TEXT,
    cycle TEXT,
    error INTEGER,
    x REAL,
    y REAL,
    theta REAL,
    mission_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(ts);

CREATE TABLE IF NOT EXISTS missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number INTEGER,
    started_at REAL,
    ended_at REAL,
    phase TEXT,
    cycle TEXT,
    error INTEGER DEFAULT 0,
    duration_s INTEGER,
    area_sqft REAL,
    battery_start INTEGER,
    battery_end INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    level TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    data TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    days TEXT NOT NULL,
    at_time TEXT NOT NULL,
    command TEXT NOT NULL DEFAULT 'start',
    created_at REAL NOT NULL,
    last_run_at REAL,
    last_result TEXT
);
"""


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        ensure_dirs()
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def init() -> None:
    _connect()


def _rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with _lock:
        cur = _connect().execute(sql, params)
        return _rows(cur)


def execute(sql: str, params: tuple = ()) -> int:
    with _lock:
        conn = _connect()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid or 0


# ---------------------------------------------------------------- appareils

def replace_devices(devices: list[dict[str, Any]]) -> None:
    now = time.time()
    with _lock:
        conn = _connect()
        conn.execute("UPDATE devices SET online = 0")
        for d in devices:
            conn.execute(
                """
                INSERT INTO devices (ip, mac, vendor, hostname, kind, label,
                                     services, evidence, online, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(ip) DO UPDATE SET
                    mac=excluded.mac, vendor=excluded.vendor, hostname=excluded.hostname,
                    kind=excluded.kind, label=excluded.label, services=excluded.services,
                    evidence=excluded.evidence, online=1, last_seen=excluded.last_seen
                """,
                (
                    d.get("ip"), d.get("mac"), d.get("vendor"), d.get("hostname"),
                    d.get("kind"), d.get("label"), json.dumps(d.get("services", [])),
                    json.dumps(d.get("evidence", [])), now,
                ),
            )
        conn.commit()


def list_devices() -> list[dict[str, Any]]:
    rows = query("SELECT * FROM devices ORDER BY ip")
    for r in rows:
        r["services"] = json.loads(r.get("services") or "[]")
        r["evidence"] = json.loads(r.get("evidence") or "[]")
    return rows


# ------------------------------------------------------------------ scans

def create_scan(subnet: str) -> int:
    return execute(
        "INSERT INTO scans (started_at, subnet) VALUES (?, ?)", (time.time(), subnet)
    )


def finish_scan(scan_id: int, report: dict[str, Any]) -> None:
    execute(
        "UPDATE scans SET finished_at=?, device_count=?, report=? WHERE id=?",
        (
            time.time(),
            len(report.get("devices", [])),
            json.dumps(report, ensure_ascii=False),
            scan_id,
        ),
    )


def last_scan() -> dict[str, Any] | None:
    rows = query("SELECT * FROM scans ORDER BY id DESC LIMIT 1")
    if not rows:
        return None
    row = rows[0]
    if row.get("report"):
        row["report"] = json.loads(row["report"])
    return row


# --------------------------------------------------------------- télémétrie

def add_telemetry(**kw: Any) -> None:
    execute(
        """INSERT INTO telemetry (ts, battery, phase, cycle, error, x, y, theta, mission_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            kw.get("ts", time.time()), kw.get("battery"), kw.get("phase"),
            kw.get("cycle"), kw.get("error"), kw.get("x"), kw.get("y"),
            kw.get("theta"), kw.get("mission_id"),
        ),
    )


def telemetry_since(ts: float, limit: int = 5000) -> list[dict[str, Any]]:
    return query(
        "SELECT * FROM telemetry WHERE ts >= ? ORDER BY ts ASC LIMIT ?", (ts, limit)
    )


# ---------------------------------------------------------------- missions

def start_mission(number: int | None, battery: int | None) -> int:
    return execute(
        "INSERT INTO missions (number, started_at, phase, cycle, battery_start) "
        "VALUES (?, ?, 'run', 'clean', ?)",
        (number, time.time(), battery),
    )


def finish_mission(mission_id: int, **kw: Any) -> None:
    execute(
        """UPDATE missions SET ended_at=?, duration_s=?, area_sqft=?, battery_end=?
           WHERE id=?""",
        (
            time.time(), kw.get("duration_s"), kw.get("area_sqft"),
            kw.get("battery_end"), mission_id,
        ),
    )


def list_missions(limit: int = 25) -> list[dict[str, Any]]:
    return query("SELECT * FROM missions ORDER BY id DESC LIMIT ?", (limit,))


def open_mission() -> dict[str, Any] | None:
    rows = query("SELECT * FROM missions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1")
    return rows[0] if rows else None


# ---------------------------------------------------------------- événements

def add_event(level: str, kind: str, message: str, data: Any = None) -> None:
    execute(
        "INSERT INTO events (ts, level, kind, message, data) VALUES (?, ?, ?, ?, ?)",
        (time.time(), level, kind, message, json.dumps(data) if data is not None else None),
    )


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    return query("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))


# ----------------------------------------------------------------- réglages

def get_setting(key: str, default: Any = None) -> Any:
    rows = query("SELECT value FROM settings WHERE key=?", (key,))
    if not rows:
        return default
    try:
        return json.loads(rows[0]["value"])
    except (TypeError, ValueError):
        return rows[0]["value"]


def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


# ------------------------------------------------------------- planifications

def _schedule_row(row: dict[str, Any]) -> dict[str, Any]:
    try:
        row["days"] = json.loads(row.get("days") or "[]")
    except (TypeError, ValueError):
        row["days"] = []
    row["enabled"] = bool(row.get("enabled"))
    return row


def list_schedules() -> list[dict[str, Any]]:
    rows = query("SELECT * FROM schedules ORDER BY at_time, id")
    return [_schedule_row(r) for r in rows]


def get_schedule(schedule_id: int) -> dict[str, Any] | None:
    rows = query("SELECT * FROM schedules WHERE id=?", (schedule_id,))
    return _schedule_row(rows[0]) if rows else None


def create_schedule(
    name: str, days: list[int], at_time: str, command: str, enabled: bool
) -> dict[str, Any]:
    new_id = execute(
        "INSERT INTO schedules (name, enabled, days, at_time, command, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, 1 if enabled else 0, json.dumps(sorted(set(days))),
         at_time, command, time.time()),
    )
    return get_schedule(new_id) or {}


def update_schedule(schedule_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {"name", "enabled", "days", "at_time", "command"}
    sets: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        if key == "days":
            value = json.dumps(sorted(set(int(d) for d in value)))
        if key == "enabled":
            value = 1 if value else 0
        sets.append(f"{key}=?")
        params.append(value)
    if not sets:
        return get_schedule(schedule_id)
    params.append(schedule_id)
    execute(f"UPDATE schedules SET {', '.join(sets)} WHERE id=?", tuple(params))
    return get_schedule(schedule_id)


def delete_schedule(schedule_id: int) -> bool:
    exists = get_schedule(schedule_id) is not None
    execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
    return exists


def mark_schedule_run(schedule_id: int, result: str) -> None:
    execute(
        "UPDATE schedules SET last_run_at=?, last_result=? WHERE id=?",
        (time.time(), result, schedule_id),
    )
