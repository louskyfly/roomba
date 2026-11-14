"""Récupération best-effort des identifiants locaux via le cloud iRobot.

Les API iRobot (authentification Gigya puis services iRobot) sont privées et
évoluent régulièrement. Cette implémentation tente le flux historiquement
documenté (dorita980 / Roomba980-Python) en s'appuyant sur la découverte
d'endpoints iRobot. En cas d'échec, l'appelant doit proposer une récupération
manuelle.

Aucun secret n'est journalisé. Les identifiants de compte ne sont utilisés que
pour cette requête ponctuelle et ne sont pas persistés.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_GIGYA_API_KEY = "3_rWtvxmUKwgOzu3AUPTMLnM46lj-LxURGflmu5PcE_sGptTbD-wMeshVbLvYpq01K"
GIGYA_LOGIN = "https://accounts.us1.gigya.com/accounts.login"
DISCOVERY_URL = "https://disc-prod.iot.irobotapi.com/v1/discover/endpoints?country_code=FR"
FALLBACK_LOGINS = [
    "https://unauth3.prod.iot.irobotapi.com/v2/login",
    "https://unauth2.prod.iot.irobotapi.com/v2/login",
    "https://unauth1.prod.iot.irobotapi.com/v2/login",
]

TIMEOUT = 20


def _post_form(url: str, data: dict[str, Any]) -> dict[str, Any]:
    body = urllib.parse.urlencode({k: v if isinstance(v, str) else json.dumps(v) for k, v in data.items()}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _post_json(url: str, data: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _discover() -> tuple[str, list[str]]:
    api_key = DEFAULT_GIGYA_API_KEY
    login_urls = list(FALLBACK_LOGINS)
    try:
        disc = _get_json(DISCOVERY_URL)
    except Exception:
        return api_key, login_urls
    gigya = disc.get("gigya") or {}
    api_key = gigya.get("api_key") or api_key
    urls: list[str] = []
    current = disc.get("current_deployment")
    deployments = disc.get("deployments") or {}
    if current and current in deployments:
        order = [current] + [k for k in deployments if k != current]
    else:
        order = list(deployments.keys())
    for key in order:
        dep = deployments.get(key) or {}
        for field in ("httpBase", "httpBaseAuth"):
            base = dep.get(field)
            if base:
                candidate = base.rstrip("/") + "/v2/login"
                if candidate not in urls:
                    urls.append(candidate)
    for url in login_urls:
        if url not in urls:
            urls.append(url)
    return api_key, urls or login_urls


def retrieve(email: str, password: str) -> dict[str, Any]:
    """Retourne {robots:[{blid,password,name,sku}], error?, detail?}."""
    api_key, login_urls = _discover()
    try:
        gigya = _post_form(
            GIGYA_LOGIN,
            {
                "apiKey": api_key,
                "targetenv": "mobile",
                "loginID": email,
                "password": password,
                "format": "json",
            },
        )
    except Exception as exc:  # noqa: BLE001
        return {"robots": [], "error": "network", "detail": f"Connexion Gigya impossible: {exc}"}

    if gigya.get("errorCode") not in (0, None):
        msg = gigya.get("errorDetails") or gigya.get("errorMessage") or str(gigya.get("errorCode"))
        return {"robots": [], "error": "auth", "detail": f"Authentification refusée: {msg}"}

    uid = gigya.get("UID")
    uid_sig = gigya.get("UIDSignature")
    sig_ts = gigya.get("signatureTimestamp")
    if not all([uid, uid_sig, sig_ts]):
        return {"robots": [], "error": "auth", "detail": "Réponse Gigya incomplète (UID/signature)."}

    gigya_obj = {"signature": uid_sig, "timestamp": sig_ts, "uid": uid}
    payload_variants: list[tuple[str, dict[str, Any]]] = [
        ("json", {"app_id": "ANDROID-C7FB240E-DF34-42D7-AE4E-A8C17079A294", "assume_robot_ownership": 0, "gigya": gigya_obj}),
        ("json", {"app_id": "ANDROID-C7FB240E-DF34-42D7-AE4E-A8C17079A294", "gigya": gigya_obj}),
        ("form", {"app_id": "ANDROID-C7FB240E-DF34-42D7-AE4E-A8C17079A294", "assume_robot_ownership": "0", "gigya": json.dumps(gigya_obj)}),
    ]

    login: dict[str, Any] | None = None
    last_exc: Exception | None = None
    for url in login_urls:
        for mode, payload in payload_variants:
            try:
                login = _post_json(url, payload) if mode == "json" else _post_form(url, payload)
                break
            except urllib.error.HTTPError as exc:
                last_exc = exc
                # 404/405 -> autre forme/endpoint peut marcher ; 5xx -> essayer suivant.
                continue
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        if login is not None:
            break
    if login is None:
        detail = str(last_exc) if last_exc else "aucun endpoint joignable"
        return {
            "robots": [],
            "error": "network",
            "detail": (
                f"Connexion iRobot impossible ({detail}). "
                "Le service cloud iRobot a peut-être changé ; récupérez les identifiants "
                "locaux manuellement (ex. get-roomba-password-cloud de dorita980) puis "
                "saisissez le BLID et le mot de passe local (:1:…)."
            ),
        }

    robots_raw = login.get("robots")
    if not robots_raw:
        robots_raw = login.get("robotCredentials") or login.get("robot_credentials") or {}

    def _looks_like_robot_blid(value: str) -> bool:
        # Un BLID robot est un identifiant hexadécimal long, jamais un e-mail.
        v = (value or "").strip()
        if "@" in v or len(v) < 8:
            return False
        return True

    robots: list[dict[str, Any]] = []
    if isinstance(robots_raw, dict):
        for key, info in robots_raw.items():
            if not isinstance(info, dict):
                continue
            blid = str(info.get("blid") or info.get("robotid") or key or "")
            pwd = info.get("password") or info.get("pwd") or info.get("blid_password")
            if not pwd or not _looks_like_robot_blid(blid):
                continue
            # Le mot de passe local iRobot commence typiquement par ":1:".
            robots.append(
                {
                    "blid": blid,
                    "password": str(pwd),
                    "name": info.get("name") or info.get("robotName"),
                    "sku": info.get("sku"),
                }
            )
    elif isinstance(robots_raw, list):
        for info in robots_raw:
            if not isinstance(info, dict):
                continue
            blid = str(info.get("blid") or info.get("robotid") or info.get("serial") or "")
            pwd = info.get("password") or info.get("pwd")
            if blid and pwd and _looks_like_robot_blid(blid):
                robots.append(
                    {
                        "blid": blid,
                        "password": str(pwd),
                        "name": info.get("name"),
                        "sku": info.get("sku"),
                    }
                )

    if not robots:
        return {
            "robots": [],
            "error": "empty",
            "detail": (
                "Authentification réussie mais aucun identifiant robot exploitable reçu. "
                "Le flux cloud iRobot a peut-être changé ; utilisez une récupération manuelle "
                "(ex. get-roomba-password-cloud de dorita980) puis saisissez le BLID/mot de passe local."
            ),
        }
    return {"robots": robots}