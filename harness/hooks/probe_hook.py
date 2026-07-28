#!/usr/bin/env python3
"""Sonda temporal: registra el payload real que Claude Code envía a un hook.

Se usa una sola vez, para documentar la forma de los payloads antes de
escribir los hooks de verdad. No forma parte del harness final.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "probe-out"


def main() -> int:
    raw = sys.stdin.read()
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S%f")
    try:
        data = json.loads(raw)
        event = data.get("hook_event_name", "sin_evento")
        text = json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        event = "no_json"
        text = raw
    (OUT / f"{event}-{stamp}.json").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
