"""Configuration centrale de ROO-LAB."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "ROO-LAB"
APP_VERSION = "0.4.0"

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("ROOLAB_DATA_DIR", BASE_DIR / "data"))
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
OUI_FILE = Path(__file__).resolve().parent / "data" / "oui.csv"

DB_PATH = DATA_DIR / "roolab.db"
SECRET_PATH = DATA_DIR / "credentials.bin"

HOST = os.environ.get("ROOLAB_HOST", "127.0.0.1")
PORT = int(os.environ.get("ROOLAB_PORT", "8000"))

# Limites de sécurité des analyses réseau.
MAX_HOSTS = 512          # jamais plus qu'un /23
PORT_SCAN_TIMEOUT = 0.65  # secondes par port
PORT_SCAN_CONCURRENCY = 64
DISCOVERY_WINDOW = 3.2    # écoute mDNS/SSDP

# Ports examinés sur les hôtes vivants (lecture seule, connexion TCP simple).
PROBE_PORTS: dict[int, str] = {
    22: "ssh",
    53: "dns",
    80: "http",
    443: "https",
    554: "rtsp",
    1883: "mqtt",
    5000: "upnp/http",
    5353: "mdns",
    8008: "http-alt",
    8080: "http-alt",
    8443: "https-alt",
    8883: "mqtts (iRobot)",
    9000: "http-alt",
    9100: "printer",
    980: "irobot-legacy",
}

# Services mDNS recherchés.
MDNS_SERVICES = [
    "_irobot._tcp.local",
    "_amzn-alexa._tcp.local",
    "_http._tcp.local",
    "_https._tcp.local",
    "_workstation._tcp.local",
    "_device-info._tcp.local",
    "_googlecast._tcp.local",
    "_airplay._tcp.local",
    "_raop._tcp.local",
    "_hap._tcp.local",
    "_matter._tcp.local",
    "_printer._tcp.local",
    "_ipp._tcp.local",
    "_spotify-connect._tcp.local",
    "_sonos._tcp.local",
    "_sleep-proxy._udp.local",
]

# Identifiants de commandes autorisées, avec libellé et niveau de risque.
COMMANDS: dict[str, dict[str, object]] = {
    "start": {"label": "Démarrer le nettoyage", "risky": True},
    "pause": {"label": "Mettre en pause", "risky": False},
    "resume": {"label": "Reprendre", "risky": False},
    "stop": {"label": "Arrêter la mission", "risky": True},
    "dock": {"label": "Retour à la station", "risky": True},
    "find": {"label": "Faire sonner le robot", "risky": False},
    "evac": {"label": "Vider le bac (Clean Base)", "risky": True},
}

# Commandes qui modifient réellement une mission en cours.
DESTRUCTIVE = {"start", "stop", "dock", "evac"}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
