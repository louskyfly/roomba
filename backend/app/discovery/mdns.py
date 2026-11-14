"""Requêtes mDNS (DNS-SD) — découverte passive des services annoncés."""

from __future__ import annotations

import asyncio
import socket
import struct
from dataclasses import dataclass, field

from ..config import DISCOVERY_WINDOW, MDNS_SERVICES

MCAST = "224.0.0.251"
PORT = 5353

TYPE_A = 1
TYPE_PTR = 12
TYPE_TXT = 16
TYPE_AAAA = 28
TYPE_SRV = 33


@dataclass
class MdnsHost:
    ip: str
    names: set[str] = field(default_factory=set)
    services: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ip": self.ip,
            "names": sorted(self.names),
            "services": self.services,
        }


def _encode_name(name: str) -> bytes:
    out = b""
    for label in name.strip(".").split("."):
        if label:
            out += bytes([len(label)]) + label.encode("ascii", "ignore")
    return out + b"\x00"


def build_query(name: str) -> bytes:
    header = struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0)
    return header + _encode_name(name) + struct.pack("!HH", TYPE_PTR, 1)


def _read_name(buf: bytes, off: int) -> tuple[str, int]:
    labels: list[str] = []
    end = off
    jumped = False
    hops = 0
    while off < len(buf) and hops < 64:
        hops += 1
        length = buf[off]
        if length == 0:
            off += 1
            if not jumped:
                end = off
            break
        if length & 0xC0 == 0xC0:
            if off + 1 >= len(buf):
                break
            ptr = ((length & 0x3F) << 8) | buf[off + 1]
            if not jumped:
                end = off + 2
            off = ptr
            jumped = True
            continue
        labels.append(buf[off + 1:off + 1 + length].decode("utf-8", "replace"))
        off += length + 1
        if not jumped:
            end = off
    return ".".join(labels), end


def parse_packet(buf: bytes) -> list[dict]:
    if len(buf) < 12:
        return []
    _, _, qd, an, _, ar = struct.unpack("!HHHHHH", buf[:12])
    off = 12
    for _ in range(qd):
        _, off = _read_name(buf, off)
        off += 4
    records: list[dict] = []
    for _ in range(an + ar):
        try:
            name, off = _read_name(buf, off)
            rtype, _, ttl, rdlen = struct.unpack("!HHIH", buf[off:off + 10])
            off += 10
            rdata = buf[off:off + rdlen]
            start = off
            off += rdlen
            rec = {"name": name, "type": rtype, "ttl": ttl, "raw": rdata}
            if rtype == TYPE_A and rdlen == 4:
                rec["data"] = socket.inet_ntoa(rdata)
            elif rtype == TYPE_AAAA and rdlen == 16:
                rec["data"] = socket.inet_ntop(socket.AF_INET6, rdata)
            elif rtype == TYPE_PTR:
                rec["data"], _ = _read_name(buf, start)
            elif rtype == TYPE_SRV:
                prio, weight, port = struct.unpack("!HHH", rdata[:6])
                target, _ = _read_name(buf, start + 6)
                rec["data"] = target
                rec["port"] = port
                rec["priority"] = prio
                rec["weight"] = weight
            elif rtype == TYPE_TXT:
                items: list[str] = []
                p = 0
                while p < len(rdata):
                    ln = rdata[p]
                    items.append(rdata[p + 1:p + 1 + ln].decode("utf-8", "replace"))
                    p += ln + 1
                rec["data"] = items
            records.append(rec)
        except (struct.error, IndexError, ValueError):
            break
    return records


async def browse(timeout: float = DISCOVERY_WINDOW) -> dict[str, MdnsHost]:
    loop = asyncio.get_running_loop()
    records: list[tuple[str, dict]] = []

    class Proto(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr) -> None:
            for rec in parse_packet(data):
                records.append((addr[0], rec))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", PORT))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                        socket.inet_aton(MCAST) + socket.inet_aton("0.0.0.0"))
    except OSError:
        sock.close()
        return {}
    sock.setblocking(False)

    transport, _ = await loop.create_datagram_endpoint(lambda: Proto(), sock=sock)
    try:
        for service in MDNS_SERVICES:
            transport.sendto(build_query(service), (MCAST, PORT))
            await asyncio.sleep(0.02)
        await asyncio.sleep(timeout)
    finally:
        transport.close()

    # index des enregistrements
    by_name: dict[str, list[dict]] = {}
    for src, rec in records:
        by_name.setdefault(rec["name"].lower(), []).append(rec)
        rec["_src"] = src

    def addr_of(name: str, seen: set[str] | None = None) -> str | None:
        seen = seen or set()
        key = name.lower()
        if key in seen:
            return None
        seen.add(key)
        for rec in by_name.get(key, []):
            if rec["type"] == TYPE_A and isinstance(rec.get("data"), str):
                return rec["data"]
        return None

    hosts: dict[str, MdnsHost] = {}

    def host_for(ip: str) -> MdnsHost:
        return hosts.setdefault(ip, MdnsHost(ip=ip))

    # services annoncés
    for rec_name, recs in list(by_name.items()):
        for ptr in recs:
            if ptr["type"] != TYPE_PTR or not isinstance(ptr.get("data"), str):
                continue
            service = rec_name
            instance = ptr["data"]
            target = None
            port = None
            txt: dict[str, str] = {}
            for r in by_name.get(instance.lower(), []):
                if r["type"] == TYPE_SRV:
                    target = r.get("data")
                    port = r.get("port")
                elif r["type"] == TYPE_TXT:
                    for item in r.get("data") or []:
                        if "=" in item:
                            k, v = item.split("=", 1)
                            txt[k] = v
            ip = addr_of(target) if target else None
            if not ip:
                ip = ptr.get("_src")
            if not ip:
                continue
            h = host_for(ip)
            label = instance
            if label.lower().endswith("." + service.lower()):
                label = label[: -(len(service) + 1)]
            h.names.add(label)
            if target:
                h.names.add(target)
            h.services.append({
                "service": service,
                "instance": instance,
                "port": port,
                "txt": txt,
            })

    # noms d'hôtes seuls (A/AAAA)
    for rec_name, recs in by_name.items():
        for rec in recs:
            if rec["type"] in (TYPE_A, TYPE_AAAA) and isinstance(rec.get("data"), str):
                if rec["data"].startswith("169.254."):
                    continue
                h = host_for(rec["data"])
                if rec["name"] and not rec["name"].startswith("_"):
                    h.names.add(rec["name"])

    return hosts
