"""Corpus statistics and source-tracked coefficients."""
import json
import math
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from paths import CATALOG

CATALOG_DATA = json.loads((CATALOG / "coefficients.json").read_text(encoding="utf-8"))

DRY_MATTER_RATIO = {
    "lettuce": 0.05, "spinach": 0.08, "kale": 0.10, "radish": 0.06,
    "tomato": 0.06, "pepper": 0.08,
    "wheat": 0.88, "rice": 0.88,
    "potato": 0.20, "soybean": 0.90,
    "spirulina": 0.07,
}
DEFAULT_DRY_MATTER = 0.10
EDIBLE_FRACTION = {
    "lettuce": 0.90, "spinach": 0.90, "kale": 0.85, "radish": 0.55,
    "tomato": 0.60, "pepper": 0.55,
    "wheat": 0.45, "rice": 0.45, "potato": 0.75, "soybean": 0.40,
    "spirulina": 1.00,
}
O2_PER_DRY_G = 1.07
CO2_PER_DRY_G = 1.47
DEFAULT_EDIBLE = CATALOG_DATA["global"]["harvest_index"]["median"]


class Coefficients:
    def __init__(self, crop: str):
        self.crop = crop
        self.stats = deepcopy(CATALOG_DATA["global"])
        crop_stats = CATALOG_DATA["per_crop"].get(crop)
        if crop_stats:
            self.stats["biomass_rate"].update(
                median=crop_stats["biomass_rate_median"],
                p25=crop_stats["p25"], p75=crop_stats["p75"],
            )
        self.values = {
            key: {"value": stat["median"], "unit": stat["unit"],
                  "source": "corpus_median", "note": f"data/catalog/coefficients.json; {crop if key == 'biomass_rate' and crop_stats else 'global'}"}
            for key, stat in self.stats.items()
        }
        for key, value, unit, source in (
            ("dry_matter", DRY_MATTER_RATIO.get(crop, DEFAULT_DRY_MATTER), "ratio", "agronomy_constant"),
            ("edible_fraction", EDIBLE_FRACTION.get(crop, DEFAULT_EDIBLE), "ratio", "agronomy_constant"),
            ("o2_per_dry_g", O2_PER_DRY_G, "g/g dry biomass", "stoichiometry"),
            ("co2_per_dry_g", CO2_PER_DRY_G, "g/g dry biomass", "stoichiometry"),
        ):
            self.values[key] = {"value": value, "unit": unit, "source": source, "note": "SPEC §4"}

    def __getitem__(self, key):
        return self.values[key]["value"]

    def plausible(self, key, value=None):
        value = self[key] if value is None else value
        stat = self.stats[key]
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and stat["p25"] / 3 <= value <= stat["p75"] * 3)

    def reset(self, key):
        self.values[key].update(value=self.stats[key]["median"], source="corpus_median")

    def as_dict(self):
        return deepcopy(self.values)

    def sources(self):
        return list(dict.fromkeys(v["source"] for v in self.values.values()
                                 if v["source"] not in {"corpus_median", "agronomy_constant", "stoichiometry"}))
