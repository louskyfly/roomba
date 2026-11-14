"""Identification heuristique des appareils à partir des indices collectés."""

from __future__ import annotations

import re

KIND_LABELS = {
    "robot": "Robot aspirateur",
    "router": "Box / routeur",
    "tv": "Téléviseur",
    "speaker": "Enceinte / média",
    "phone": "Téléphone",
    "computer": "Ordinateur",
    "iot": "Objet connecté",
    "printer": "Imprimante",
    "nas": "Stockage réseau",
    "unknown": "Inconnu",
}


def _contains(value: str | None, *needles: str) -> bool:
    if not value:
        return False
    low = value.lower()
    return any(n.lower() in low for n in needles)


def _clean_local(name: str | None) -> str | None:
    if not name:
        return None
    return name[:-6] if name.lower().endswith(".local") else name


_ID_RE = re.compile(
    r"^(?:[0-9a-f]{16,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
    re.IGNORECASE,
)


def _looks_like_id(value: str | None) -> bool:
    """Un nom d'instance mDNS qui n'est en réalité qu'un identifiant technique."""
    return bool(value) and bool(_ID_RE.fullmatch(value.strip()))


_TV_BRANDS = {
    "samsung": "Samsung",
    "lg": "LG",
    "sony": "Sony",
    "philips": "Philips",
    "hisense": "Hisense",
}


def identify(host: dict) -> dict:
    """Retourne {kind, label, hostname, evidence[]} — jamais de donnée inventée."""
    ip = host["ip"]
    mac = host.get("mac")
    vendor = host.get("vendor") or ""
    mdns = host.get("mdns") or {}
    ssdp = host.get("ssdp") or {}
    ports = {p["port"] for p in host.get("ports", [])}
    tls = host.get("tls") or {}
    device = ssdp.get("device") or {}
    evidence: list[str] = []

    mdns_names = [n for n in (mdns.get("names") or []) if n]
    instances: list[str] = []
    for service in mdns.get("services", []):
        label = service.get("instance") or ""
        suffix = "." + (service.get("service") or "")
        if suffix != "." and label.lower().endswith(suffix.lower()):
            label = label[: -len(suffix)]
        if label and label not in instances:
            instances.append(label)

    hostname = None
    for name in mdns_names:
        cleaned = _clean_local(name)
        if cleaned and not cleaned.startswith("_"):
            hostname = cleaned
            break
    if not hostname and device.get("friendlyName"):
        hostname = device["friendlyName"]

    friendly = next((name for name in instances if not _looks_like_id(name)), None)
    services = [s.get("service", "") for s in mdns.get("services", [])]

    kind = "unknown"
    label = friendly or hostname or vendor or ip
    confidence = "low"

    # --- cet ordinateur
    if host.get("self"):
        kind = "computer"
        label = hostname or "Cet ordinateur"
        evidence.append("Interface réseau locale de cette machine")
        confidence = "high"

    # --- iRobot : OUI, certificat, mDNS constructeur, port MQTT local
    else:
        robot_score = 0
        if _contains(vendor, "irobot"):
            robot_score += 2
            evidence.append(
                f"OUI {('' if not mac else mac[:8].upper())} attribué à iRobot Corporation"
            )
        if _contains(tls.get("organization"), "irobot") or _contains(
            tls.get("common_name"), "irobot-"
        ):
            robot_score += 3
            evidence.append(
                f"Certificat TLS iRobot (CN {tls.get('common_name')}, "
                f"signé « {tls.get('issuer_cn') or 'iRobot'} », valide jusqu'au "
                f"{tls.get('not_after')})"
            )
        if any("irobot" in (n or "").lower() for n in mdns_names + instances):
            robot_score += 1
            evidence.append("Nom mDNS iRobot-… annoncé sur le réseau")
        if 8883 in ports:
            robot_score += 1
            evidence.append("Broker MQTT/TLS local actif sur le port 8883 (protocole v3)")

        if robot_score >= 2:
            kind = "robot"
            confidence = "high" if robot_score >= 4 else "medium"
            label = "Roomba"
            for name in instances + mdns_names:
                if "irobot-" in name.lower():
                    short = name.lower().split("irobot-", 1)[1][:6].upper()
                    label = f"Roomba · {short}"
                    break

        elif _contains(vendor, "freebox") or _contains(
            device.get("manufacturer"), "freebox"
        ):
            if _contains(friendly, "player") or _contains(hostname, "player"):
                kind = "tv"
                label = friendly or hostname or "Freebox Player"
                evidence.append("Lecteur multimédia Freebox (UPnP/mDNS)")
            else:
                kind = "router"
                label = friendly or hostname or "Freebox Server"
                evidence.append("Constructeur Freebox SAS — box internet du réseau")
            confidence = "high"

        elif _contains(device.get("deviceType"), "MediaRenderer") or _contains(
            device.get("manufacturer"), "samsung", "lg", "sony", "philips", "hisense"
        ) or any("airplay" in s for s in services):
            kind = "tv"
            brand = next(
                (
                    name
                    for needle, name in _TV_BRANDS.items()
                    if _contains(vendor, needle) or _contains(device.get("manufacturer"), needle)
                ),
                None,
            )
            label = friendly or hostname or (f"Téléviseur {brand}" if brand else "Téléviseur")
            confidence = "high"
            if device.get("manufacturer"):
                evidence.append(
                    f"UPnP : {device.get('manufacturer')} {device.get('modelName', '')}".strip()
                )

        elif any("googlecast" in s or "raop" in s or "sonos" in s for s in services):
            kind = "speaker"
            label = friendly or hostname or "Enceinte / média"
            evidence.append("Service mDNS de diffusion média")
            confidence = "medium"

        elif any("hap" in s for s in services):
            kind = "iot"
            label = friendly or hostname or "Accessoire HomeKit"
            evidence.append("Service mDNS HomeKit (_hap._tcp)")
            confidence = "high"

        elif _contains(vendor, "espressif"):
            kind = "iot"
            label = friendly or hostname or "ESP32 / objet connecté"
            evidence.append("Puce Wi-Fi Espressif")
            confidence = "medium"

        elif _contains(vendor, "tuya"):
            kind = "iot"
            label = friendly or hostname or "Objet connecté (Tuya)"
            evidence.append("Module Wi-Fi Tuya Smart")
            confidence = "medium"

        elif _contains(vendor, "amazon"):
            kind = "iot"
            label = friendly or hostname or "Appareil Amazon"
            evidence.append("Constructeur Amazon Technologies")
            confidence = "medium"

        elif _contains(vendor, "apple"):
            kind = "computer"
            label = friendly or hostname or "Appareil Apple"
            evidence.append("Constructeur Apple")
            confidence = "medium"

        elif 9100 in ports or 631 in ports:
            kind = "printer"
            label = friendly or hostname or "Imprimante"
            evidence.append("Port d'impression exposé")
            confidence = "medium"

    if kind == "unknown" and not friendly and not hostname:
        label = "Appareil inconnu"

    if host.get("locally_administered"):
        evidence.append("Adresse MAC aléatoire (protection de la vie privée Wi-Fi)")

    for service in mdns.get("services", []):
        txt = service.get("txt") or {}
        if txt.get("dsn"):
            evidence.append(f"mDNS TXT dsn={txt['dsn']}")
        if service.get("service") == "_amzn-alexa._tcp.local":
            evidence.append("Service _amzn-alexa._tcp (appairage Wi-Fi simplifié)")

    return {
        "ip": ip,
        "mac": mac,
        "vendor": vendor or None,
        "hostname": hostname,
        "kind": kind,
        "kind_label": KIND_LABELS.get(kind, KIND_LABELS["unknown"]),
        "label": label,
        "confidence": confidence,
        "evidence": evidence,
    }
