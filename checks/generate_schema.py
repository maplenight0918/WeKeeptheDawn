"""Regenerate the shared plan schema: python -m checks.generate_schema [--check]."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.domain.models import tick_plan_schema


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "shared" / "tick_plan.schema.json"
    generated = json.dumps(tick_plan_schema(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != generated:
            raise SystemExit("tick_plan.schema.json is stale; run python -m checks.generate_schema")
        print("tick_plan.schema.json matches models and the crop catalog")
    else:
        target.write_text(generated, encoding="utf-8")
        print("Generated shared/tick_plan.schema.json from models and crops.json")


if __name__ == "__main__":
    main()
