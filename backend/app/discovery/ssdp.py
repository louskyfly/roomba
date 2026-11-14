"""Découverte SSDP (UPnP) : M-SEARCH standard puis lecture du descripteur XML."""

from __future__ import annotations

import asyncio
import base64
import socket
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from ..config import DISCOVERY_WINDOW

MCAST = "239.255.255.250"
PORT = 1900


def _parse_headers(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def _parse_device_xml(body: bytes) -> dict[str, str]:
    try:
        root = ET.fromstring(body.decode("utf-8", "replace"))
    except ET.ParseError:
        return {}
    wanted = {"friendlyName", "manufacturer", "modelName", "modelNumber",
              "deviceType", "serialNumber", "UDN"}
    out: dict[str, str] = {}
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag in wanted and node.text and tag not in out:
            out[tag] = node.text.strip()
    return out


async def _fetch_description(url: str, timeout: float = 2.0) -> dict[str, str]:
    """GET HTTP en lecture seule du descripteur UPnP annoncé par l'appareil."""
    try:
        u = urlparse(url)
        if u.scheme != "http" or not u.hostname:
            return {}
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(u.hostname, u.port or 80), timeout
        )
        try:
            path = (u.path or "/") + (("?" + u.query) if u.query else "")
            req = (
                f"GET {path} HTTP/1.1\r\nHost: {u.hostname}\r\n"
                "User-Agent: ROO-LAB/0.3\r\nConnection: close\r\n\r\n"
            )
            writer.write(req.encode())
            await writer.drain()
            raw = await asyncio.wait_for(reader.read(65536), timeout)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        body = raw.split(b"\r\n\r\n", 1)[-1]
        return _parse_device_xml(body)
    except Exception:
        return {}


async def discover(timeout: float = DISCOVERY_WINDOW) -> dict[str, dict]:
    loop = asyncio.get_running_loop()
    responses: list[tuple[str, str]] = []

    class Proto(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr) -> None:
            text = data.decode("latin1", "replace")
            if text.startswith(("HTTP/1.1 200", "NOTIFY", "HTTP/1.0 200")):
                responses.append((addr[0], text))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", 0))
    sock.setblocking(False)
    transport, _ = await loop.create_datagram_endpoint(lambda: Proto(), sock=sock)
    try:
        msg = (
            "M-SEARCH * HTTP/1.1\r\n"
            f"HOST: {MCAST}:{PORT}\r\n"
            'MAN: "ssdp:discover"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n'
        )
        for _ in range(2):
            transport.sendto(msg.encode(), (MCAST, PORT))
            await asyncio.sleep(0.4)
        await asyncio.sleep(timeout)
    finally:
        transport.close()

    hosts: dict[str, dict] = {}
    for ip, text in responses:
        headers = _parse_headers(text)
        host = hosts.setdefault(ip, {"ip": ip, "entries": [], "names": set()})
        entry = {
            "st": headers.get("st", "") or headers.get("nt", ""),
            "server": headers.get("server", ""),
            "location": headers.get("location", ""),
            "usn": headers.get("usn", ""),
        }
        friendly = headers.get("x-friendly-name", "")
        if friendly:
            try:
                host["names"].add(base64.b64decode(friendly).decode("utf-8", "replace"))
            except Exception:
                host["names"].add(friendly)
        if entry["location"] and not host.get("description"):
            host["description"] = entry["location"]
        if entry["st"] and entry not in host["entries"]:
            host["entries"].append(entry)

    async def enrich(host: dict) -> None:
        loc = host.get("description")
        if not loc:
            return
        info = await _fetch_description(loc)
        if info:
            host["device"] = info
            if info.get("friendlyName"):
                host["names"].add(info["friendlyName"])

    await asyncio.gather(*(enrich(h) for h in hosts.values() if h["description"]))
    for h in hosts.values():
        h["names"] = sorted(h["names"])
    return hosts
