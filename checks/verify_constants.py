"""Print every numeric source leaf and calculated yields for guide comparison."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.domain.config import (CROPS, RAW_CONSTANTS, RAW_CROPS,
                                   crop_yield_g, crew_consumption_per_tick, harvest_food)


def numeric_leaves(node: Any, path: str = ""):
    if isinstance(node, dict):
        if "value" in node:
            assert set(node) == {"value", "unit", "source"}, path
            assert node["source"].startswith("guide §"), path
            assert isinstance(node["value"], (int, float)), path
            yield path, node
        else:
            for key, value in node.items():
                yield from numeric_leaves(value, f"{path}.{key}" if path else key)
    elif isinstance(node, (int, float)):
        raise AssertionError(f"Unannotated numeric constant: {path}")


def main() -> None:
    count = 0
    for filename, data in (("world_constants.json", RAW_CONSTANTS), ("crops.json", RAW_CROPS)):
        for path, entry in numeric_leaves(data):
            print(f"{filename}:{path} = {entry['value']} {entry['unit']} [{entry['source']}]")
            count += 1
    for crop in CROPS:
        print(f"DERIVED {crop}: {crop_yield_g(crop):.12g} g -> {harvest_food(crop):.12g} game_kcal")
    print(f"DERIVED crew per tick: {crew_consumption_per_tick()}")
    print(f"Verified annotations for {count} numeric parameters. Compare printed values with cited guide tables.")


if __name__ == "__main__":
    main()
