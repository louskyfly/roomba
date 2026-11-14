"""Orchestration de l'analyse réseau (phase 1)."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import time
import urllib.request
from typing import Awaitable, Callable

from .. import db
from . import mdns, ports, ssdp
from .identify import identify
from .network import (
    Interface,
    arp_sweep,
    format_mac,
    is_locally_administered,
    primary_interface,
    vendor_for,
)

Progress = Callable[[str, int, str], None]

ONLINE_VENDOR_API = "https://api.maclookup.app/v2/macs/{prefix}"


async def lookup_vendor_online(mac: str) -> str | None:
    """Résolution OUI en ligne optionnelle (3 octets seulement, jamais l'IP)."""
    prefix = (mac or "").replace(":", "").replace("-", "")[:6]
    if len(prefix) != 6:
        return None
    url = ONLINE_VENDOR_API.format(prefix=prefix.upper())
    try:
        def fetch() -> str | None:
            req = urllib.request.Request(url, headers={"User-Agent": "ROO-LAB/0.3"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode())
            return data.get("company") or None
        name = await asyncio.wait_for(asyncio.to_thread(fetch), 4.0)
        return name
    except Exception:
        return None


async def scan(
    emit: Progress | None = None,
    allow_online_vendor: bool = False,
    interface: Interface | None = None,
) -> dict:
    def progress(step: str, pct: int, msg: str) -> None:
        if emit:
            emit(step, pct, msg)

    iface = interface or primary_interface()
    if iface is None:
        raise RuntimeError("Aucune interface réseau active détectée")

    started = time.time()
    scan_id = db.create_scan(iface.subnet)

    progress("interface", 4, f"Interface {iface.name} — {iface.ip}/{iface.prefix}")
    network = iface.network

    progress("arp", 12, f"Résolution ARP du sous-réseau {network}")
    arp_task = asyncio.create_task(arp_sweep(network))
    progress("discovery", 18, "Requêtes mDNS et SSDP (lecture seule)")
    mdns_task = asyncio.create_task(mdns.browse())
    ssdp_task = asyncio.create_task(ssdp.discover())

    arp = await arp_task
    progress("arp", 38, f"{len(arp)} entrées ARP")

    mdns_hosts, ssdp_hosts = await asyncio.gather(mdns_task, ssdp_task)
    progress("discovery", 52, f"{len(mdns_hosts)} réponses mDNS, {len(ssdp_hosts)} en SSDP")

    live_ips = sorted(
        {
            ip for ip in set(arp) | set(mdns_hosts) | set(ssdp_hosts)
            if _usable_host(ip, network)
        },
        key=_ip_key,
    )
    if iface.ip not in live_ips:
        live_ips.append(iface.ip)

    total = max(len(live_ips), 1)
    raw_hosts: list[dict] = []
    done = 0
    lock = asyncio.Lock()

    async def analyse(ip: str) -> dict:
        nonlocal done
        is_self = ip == iface.ip
        mac = iface.mac if is_self else arp.get(ip)
        vendor = vendor_for(mac)
        host = {
            "ip": ip,
            "mac": format_mac(mac) if mac else None,
            "vendor": vendor,
            "self": is_self,
            "locally_administered": is_locally_administered(mac),
            "mdns": mdns_hosts[ip].to_dict() if ip in mdns_hosts else None,
            "ssdp": _trim_ssdp(ssdp_hosts.get(ip)),
            "ports": [],
            "tls": None,
        }
        probe = await ports.scan_host(ip)
        host["ports"] = probe
        open_ports = {p["port"] for p in probe}
        if 8883 in open_ports:
            host["tls"] = await ports.tls_identity(ip, 8883)
        elif 443 in open_ports:
            host["tls"] = await ports.tls_identity(ip, 443)
        async with lock:
            done += 1
            progress("probe", 52 + int(40 * done / total),
                     f"Analyse de {ip} ({done}/{total})")
        return host

    raw_hosts = list(await asyncio.gather(*(analyse(ip) for ip in live_ips)))

    if allow_online_vendor:
        progress("vendor", 94, "Résolution des constructeurs inconnus (OUI uniquement)")
        for host in raw_hosts:
            if host["mac"] and not host["vendor"]:
                name = await lookup_vendor_online(host["mac"])
                if name:
                    host["vendor"] = name
                    from .network import remember_vendor
                    remember_vendor(host["mac"], name)

    devices = []
    for host in raw_hosts:
        info = identify(host)
        info.update({
            "self": host.get("self", False),
            "ports": host["ports"],
            "tls": host["tls"],
            "mdns": host["mdns"],
            "ssdp": host["ssdp"],
            "locally_administered": host["locally_administered"],
        })
        devices.append(info)

    devices.sort(key=lambda d: (d["kind"] != "robot", _ip_key(d["ip"])))

    report = {
        "started_at": started,
        "finished_at": time.time(),
        "duration_s": round(time.time() - started, 2),
        "interface": iface.to_dict(),
        "subnet": iface.subnet,
        "hosts_found": len(devices),
        "robot": next((d for d in devices if d["kind"] == "robot"), None),
        "devices": devices,
    }

    db.replace_devices(devices)
    db.finish_scan(scan_id, report)
    progress("done", 100, f"{len(devices)} appareils identifiés")
    if report["robot"]:
        db.add_event("info", "network", "Roomba détecté sur le réseau",
                     {"ip": report["robot"]["ip"]})
    return report


def _in_network(ip: str, network: ipaddress.IPv4Network) -> bool:
    try:
        return ipaddress.IPv4Address(ip) in network
    except ValueError:
        return False


def _usable_host(ip: str, network: ipaddress.IPv4Network) -> bool:
    """Exclut réseau, broadcast et multicast : seuls de vrais hôtes."""
    try:
        addr = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    if addr not in network or addr.is_multicast:
        return False
    return addr not in (network.network_address, network.broadcast_address)


def _trim_ssdp(host: dict | None) -> dict | None:
    if not host:
        return None
    return {
        "ip": host.get("ip"),
        "names": host.get("names", []),
        "device": host.get("device"),
        "entries": host.get("entries", [])[:4],
    }


def _ip_key(ip: str) -> tuple:
    try:
        return tuple(int(p) for p in ip.split("."))
    except ValueError:
        return (999, 999, 999, 999)
