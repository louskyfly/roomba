"""Découverte réseau locale, non intrusive.

Aucune tentative d'authentification, aucun paquet forgé au-delà des requêtes de
découverte standard (ARP passif, mDNS, SSDP, connexion TCP simple).
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
import subprocess
import sys

from ..config import MAX_HOSTS, OUI_FILE

# ------------------------------------------------------------------ interfaces


class Interface:
    def __init__(self, name: str, ip: str, prefix: int,
                 mac: str | None = None, gateway: str | None = None):
        self.name = name
        self.ip = ip
        self.prefix = prefix
        self.mac = mac
        self.gateway = gateway

    @property
    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Network(f"{self.ip}/{self.prefix}", strict=False)

    @property
    def subnet(self) -> str:
        return str(self.network)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ip": self.ip,
            "prefix": self.prefix,
            "mac": self.mac,
            "gateway": self.gateway,
            "subnet": self.subnet,
            "broadcast": str(self.network.broadcast_address),
        }


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    try:
        out = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return out.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _windows_interfaces() -> list[Interface]:
    script = (
        "Get-NetIPConfiguration | Where-Object { $_.NetAdapter.Status -eq 'Up' "
        "} | ForEach-Object { [pscustomobject]@{ alias=$_.InterfaceAlias; "
        "ip=$_.IPv4Address.IPAddress; prefix=$_.IPv4Address.PrefixLength; "
        "mac=$_.NetAdapter.MacAddress; gw=($_.IPv4DefaultGateway.NextHop) } } "
        "| ConvertTo-Json -Compress"
    )
    raw = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    out: list[Interface] = []
    for item in data:
        ip = item.get("ip")
        if not ip or ip.startswith("127."):
            continue
        prefix = item.get("prefix") or 24
        gw = item.get("gw")
        if isinstance(gw, list):
            gw = gw[0] if gw else None
        mac = item.get("mac")
        out.append(Interface(item.get("alias") or "?", ip, int(prefix),
                             mac.replace("-", ":").lower() if mac else None, gw))
    return out


def _posix_interfaces() -> list[Interface]:
    out: list[Interface] = []
    raw = _run(["ip", "-4", "-o", "addr", "show"])
    default = _run(["ip", "route", "show", "default"])
    gw = None
    m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", default)
    if m:
        gw = m.group(1)
    for line in raw.splitlines():
        m = re.search(r"\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
        if not m:
            continue
        dev, ip, prefix = m.group(1), m.group(2), int(m.group(3))
        if ip.startswith("127."):
            continue
        try:
            mac = open(f"/sys/class/net/{dev}/address").read().strip() or None
        except OSError:
            mac = None
        out.append(Interface(dev, ip, prefix, mac, gw))
    return out


def _socket_fallback() -> list[Interface]:
    ip = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        return []
    if not ip or ip.startswith("127."):
        return []
    return [Interface("default", ip, 24)]


def get_interfaces() -> list[Interface]:
    if sys.platform == "win32":
        found = _windows_interfaces()
    elif sys.platform.startswith("linux"):
        found = _posix_interfaces()
    else:
        found = []
    if not found:
        found = _socket_fallback()
    # exclut les liens locaux (APIPA) et les réseaux trop grands
    return [
        i for i in found
        if not i.ip.startswith("169.254.") and i.network.num_addresses <= 1024
    ]


def primary_interface() -> Interface | None:
    ifaces = get_interfaces()
    with_gw = [i for i in ifaces if i.gateway]
    return (with_gw or ifaces or [None])[0]


# ------------------------------------------------------------------ table ARP

_MAC_RE = r"([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})"
_IP_RE = r"(\d{1,3}(?:\.\d{1,3}){3})"


def read_arp_table() -> dict[str, str]:
    """Retourne {ip: mac} depuis le cache ARP du système."""
    text = ""
    if sys.platform == "win32":
        text = _run(["arp", "-a"])
    else:
        text = _run(["ip", "neigh"]) or _run(["arp", "-an"])
    table: dict[str, str] = {}
    for line in text.splitlines():
        m = re.search(_IP_RE + r"\s+" + _MAC_RE, line)
        if m:
            ip, mac = m.group(1), m.group(2)
        else:
            m = re.search(_MAC_RE + r".*?" + _IP_RE, line)
            if not m:
                continue
            mac, ip = m.group(1), m.group(2)
        table[ip] = normalize_mac(mac)
    return table


def normalize_mac(mac: str) -> str:
    return re.sub(r"[^0-9a-f]", "", mac.lower()).ljust(12, "0")[:12]


def format_mac(raw: str) -> str:
    m = normalize_mac(raw)
    return ":".join(m[i:i + 2] for i in range(0, 12, 2))


async def arp_sweep(network: ipaddress.IPv4Network) -> dict[str, str]:
    """Force la résolution ARP de chaque hôte avec un unique datagramme UDP.

    Aucun port n'est scanné ici : on envoie 1 octet vers le port 9 (discard),
    ce qui suffit à peupler le cache ARP local.
    """
    hosts = list(network.hosts())[:MAX_HOSTS]
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, local_addr=("0.0.0.0", 0)
    )
    try:
        for idx, host in enumerate(hosts):
            try:
                transport.sendto(b"\x00", (str(host), 9))
            except OSError:
                pass
            if idx % 24 == 23:
                await asyncio.sleep(0.02)
        await asyncio.sleep(1.6)
    finally:
        transport.close()
    return read_arp_table()


# --------------------------------------------------------------- base OUI

_vendors: dict[str, str] | None = None


def vendors() -> dict[str, str]:
    global _vendors
    if _vendors is None:
        _vendors = {}
        try:
            with open(OUI_FILE, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(",", 1)
                    if len(parts) == 2:
                        _vendors[parts[0].strip().upper()] = parts[1].strip()
        except OSError:
            _vendors = {}
    return _vendors


def vendor_for(mac: str | None) -> str | None:
    if not mac:
        return None
    prefix = normalize_mac(mac)[:6].upper()
    return vendors().get(prefix)


def is_locally_administered(mac: str | None) -> bool:
    if not mac:
        return False
    try:
        return bool(int(normalize_mac(mac)[:2], 16) & 0x02)
    except ValueError:
        return False


def remember_vendor(mac: str, name: str) -> None:
    prefix = normalize_mac(mac)[:6].upper()
    if not prefix or not name:
        return
    vendors()[prefix] = name
    try:
        with open(OUI_FILE, "a", encoding="utf-8") as fh:
            fh.write(f"{prefix},{name}\n")
    except OSError:
        pass
