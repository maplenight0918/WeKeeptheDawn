"""Deterministic resource conversion; SPEC §4 and §11."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from paths import ROOT

def temp_factor(t, opt=22.0, width=11.0):
    return max(0.0, math.exp(-((t - opt) / width) ** 2))

def co2_factor(ppm, ref=400.0):
    km = 300.0
    f = (ppm / (ppm + km)) / (ref / (ref + km))
    return max(0.1, min(f, 1.8))

def humidity_factor(rh):
    if 50 <= rh <= 70:
        return 1.0
    if rh < 50:
        return max(0.6, 1.0 - (50 - rh) * 0.008)    # 到 0% 時 0.6
    return max(0.6, 1.0 - (rh - 70) * 0.010)        # 到 100% 時 0.7，被 max 夾住

def density_factor(density, optimal=27.0):
    if density <= 0:
        return 0.0
    r = density / optimal
    return min(1.15, r / (0.35 + 0.65 * r))

def light_response(dli, ref=12.9, km=9.0):
    if dli <= 0:
        return 0.0
    return (dli / (dli + km)) / (ref / (ref + km))


LED_EFFICACY = 2.3
HVAC_FRACTION = 0.45
PUMP_W_PER_M2 = 8.0
WATER_RECOVERY = 0.92


def simulate(coeffs, inp):
    p = inp.model_dump() if hasattr(inp, "model_dump") else dict(inp)
    warnings = []
    for key in ["biomass_rate", "lue", "wue", "led_power", "transpiration", "growth_days"]:
        if not coeffs.plausible(key):
            warnings.append(f"{key}={coeffs[key]} 超出 corpus P25/3–P75×3 合理範圍。")
    area, ppfd = p["area"], p["ppfd"]

    def power(light):
        return (light * area / LED_EFFICACY * (1 + HVAC_FRACTION) + PUMP_W_PER_M2 * area) / 1000

    requested_power = power(ppfd)
    budget = p.get("power_budget")
    if budget is not None and requested_power > budget:
        ppfd = max(0.0, (budget * 1000 - PUMP_W_PER_M2 * area) * LED_EFFICACY / (area * (1 + HVAC_FRACTION)))
        warnings.append(f"需求 {requested_power:.2f} kW 超出預算 {budget:g} kW，PPFD 降到 {ppfd:.0f} µmol/m²/s。")
        if budget < power(0):
            warnings.append(f"預算不足以供應泵的最低需求 {power(0):.2f} kW；PPFD 已降為 0，仍無法滿足預算。")
    dli = ppfd * p["photoperiod"] * 3600 / 1e6
    f_temp = temp_factor(p["temperature"])
    f_co2 = co2_factor(p["co2"])
    f_humidity = humidity_factor(p["humidity"])
    f_density = density_factor(p["density"])
    env = f_temp * f_co2 * f_humidity * f_density
    light = light_response(dli)
    fresh = coeffs["biomass_rate"] * area * env * light
    dry = fresh * coeffs["dry_matter"]
    edible = fresh * coeffs["edible_fraction"]
    o2 = dry * coeffs["o2_per_dry_g"] / 1000
    co2 = dry * coeffs["co2_per_dry_g"] / 1000
    water = coeffs["transpiration"] * area * env * light
    power_kw = power(ppfd)
    lue_dry = dli * coeffs["lue"] * area * env
    wue_water = dry / coeffs["wue"] if coeffs["wue"] > 0 else 0.0
    for name, measured, check in [("LUE 乾重", dry, lue_dry), ("WUE 蒸散", water, wue_water)]:
        if min(measured, check) > 0 and max(measured, check) / min(measured, check) > 4:
            warnings.append(f"{name}交叉驗算相差超過 4 倍（主路徑 {measured:.2f}，交叉值 {check:.2f}），保留文獻錨定值。")
    health = f_temp * f_humidity * min(f_co2, 1.0)
    if dli < 5:
        health *= 0.6
    health = round(min(max(health, 0.0), 1.0), 3)
    return {
        "supply": {"o2_kg_day": o2, "edible_g_day": edible, "biomass_g_day": fresh,
                   "dry_biomass_g_day": dry, "water_recycled_l_day": water * WATER_RECOVERY},
        "demand": {"power_kw": power_kw, "water_l_day": water, "co2_kg_day": co2},
        "health": health,
        "daily_rate": {
            "o2_kg_per_day": round(o2, 4),
            "edible_g_per_day": round(edible, 1),
            "water_l_per_day": round(water, 2),
            "power_kwh_per_day": round(power_kw * 24, 2),
            "co2_kg_per_day": round(co2, 4),
        },
        "factors": {"temperature": f_temp, "co2": f_co2, "humidity": f_humidity, "density": f_density},
        "intermediate": {"dli": dli, "effective_ppfd": round(ppfd, 1), "env_factor": env,
                         "light_response": light, "fresh_g_day": fresh,
                         "lue_dry_g_day": lue_dry, "wue_water_l_day": wue_water},
        "warnings": warnings, "coefficients": coeffs.as_dict(),
    }


def sweep_ppfd(coeffs, inp, levels):
    p = inp.model_dump() if hasattr(inp, "model_dump") else dict(inp)
    # Compare unconstrained requested operating points (SPEC §6 / §11).
    p["power_budget"] = None
    points = list(dict.fromkeys([p["ppfd"], *levels]))
    rows = []
    for ppfd in points:
        result = simulate(coeffs, {**p, "ppfd": ppfd})
        row = {"ppfd": ppfd, "power_kw": result["demand"]["power_kw"],
               "edible_g_day": result["supply"]["edible_g_day"],
               "o2_kg_day": result["supply"]["o2_kg_day"],
               "water_l_day": result["demand"]["water_l_day"], "health": result["health"],
               "power_delta_pct": None, "edible_delta_pct": None}
        if rows:
            for output, value in [("power_delta_pct", "power_kw"), ("edible_delta_pct", "edible_g_day")]:
                base = rows[0][value]
                row[output] = round((row[value] / base - 1) * 100, 1) if base else None
        rows.append(row)
    return rows
