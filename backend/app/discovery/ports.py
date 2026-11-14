"""Sondage TCP en lecture seule + empreinte TLS (identification du Roomba)."""

from __future__ import annotations

import asyncio
import ssl

from ..config import PORT_SCAN_CONCURRENCY, PORT_SCAN_TIMEOUT, PROBE_PORTS


async def probe_port(ip: str, port: int, timeout: float = PORT_SCAN_TIMEOUT) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def scan_host(ip: str, ports: dict[int, str] | None = None) -> list[dict]:
    """Teste quelques ports TCP. Un simple handshake, aucun payload applicatif."""
    table = ports or PROBE_PORTS
    sem = asyncio.Semaphore(PORT_SCAN_CONCURRENCY)

    async def one(port: int) -> dict | None:
        async with sem:
            if await probe_port(ip, port):
                return {"port": port, "service": table[port], "state": "open"}
        return None

    results = await asyncio.gather(*(one(p) for p in table))
    return [r for r in results if r]


def _decode_cert(der: bytes) -> dict[str, str]:
    try:
        from cryptography import x509
        cert = x509.load_der_x509_certificate(der)
        def name(attr) -> str | None:
            if not attr:
                return None
            return attr.rfc4514_string()
        return {
            "subject": name(cert.subject),
            "issuer": name(cert.issuer),
            "common_name": _attr(cert.subject, "commonName"),
            "organization": _attr(cert.subject, "organizationName"),
            "issuer_cn": _attr(cert.issuer, "commonName"),
            "not_after": cert.not_valid_after_utc.strftime("%Y-%m-%d"),
        }
    except Exception:
        return {}


def _attr(name, oid_name: str) -> str | None:
    try:
        from cryptography.x509.oid import NameOID
        oid = getattr(NameOID, _OID_NAMES[oid_name])
        values = name.get_attributes_for_oid(oid)
        return values[0].value if values else None
    except Exception:
        return None


_OID_NAMES = {
    "commonName": "COMMON_NAME",
    "organizationName": "ORGANIZATION_NAME",
}


async def tls_identity(ip: str, port: int = 8883, timeout: float = 3.0) -> dict:
    """Récupère le certificat présenté par l'appareil. Aucune authentification."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, ssl=ctx), timeout
        )
        try:
            ssl_object = writer.get_extra_info("ssl_object")
            cert = ssl_object.getpeercert(binary_form=True) if ssl_object else None
            cipher = writer.get_extra_info("cipher")
            version = ssl_object.version() if ssl_object is not None else None
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        out = {
            "port": port,
            "tls": version,
            "cipher": cipher[0] if cipher else None,
        }
        if cert:
            out.update(_decode_cert(cert))
        return out
    except Exception as exc:
        return {"port": port, "error": type(exc).__name__}
