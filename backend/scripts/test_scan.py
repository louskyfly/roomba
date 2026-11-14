"""Exécute une analyse réseau et affiche le rapport (sans serveur).

Usage :
    python backend/scripts/test_scan.py [--out rapport.json]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.discovery import scan  # noqa: E402


async def main() -> None:
    report = await scan(emit=lambda s, p, m: print(f"[{p:3d}%] {m}", flush=True))
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
        out.write_text(text, encoding="utf-8")
        print(f"→ {out}")
    else:
        print(text)


if __name__ == "__main__":
    asyncio.run(main())
