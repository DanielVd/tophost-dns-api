"""Evaluate read-only canary escalation from sanitized run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tophost_api.canary_policy import transient_streak


def read_exit_code(path: Path) -> int | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        value = data.get("exit_code")
        if type(value) is not int or value not in {0, 10, 20, 30}:
            return None
        return value
    except (OSError, UnicodeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("current", type=Path)
    parser.add_argument("previous", nargs="*", type=Path)
    args = parser.parse_args()

    current = read_exit_code(args.current)
    if current is None:
        print("::error::Canary result missing or invalid")
        return 1

    if current == 0:
        print("Canary compatible")
        return 0

    if current == 20:
        print("::error::Tophost authentication/configuration attention")
        return 1

    if current == 30:
        print("::error::Tophost upstream compatibility drift")
        return 1

    history = [read_exit_code(path) for path in args.previous]
    count = transient_streak(current, history)
    if count >= 3:
        print(f"::error::Tophost transient failure for {count} consecutive scheduled runs")
        return 1

    print(f"::warning::Tophost transient failure ({count}/3 consecutive scheduled runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
