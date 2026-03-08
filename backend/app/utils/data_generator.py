"""
Realistic data simulator for the Rural Microgrid.
13 consumers: clinic, school, pump, house_1 … house_10
"""
import numpy as np
from datetime import datetime
from typing import List, Dict


HOUSE_PROFILES = {
    "clinic":   {"base": 3.2, "peak_hour": 10, "peak_mult": 1.8, "priority": "critical"},
    "school":   {"base": 2.5, "peak_hour": 11, "peak_mult": 2.0, "priority": "high"},
    "pump":     {"base": 1.8, "peak_hour":  6, "peak_mult": 2.5, "priority": "high"},
    "house_1":  {"base": 0.9, "peak_hour": 19, "peak_mult": 2.2, "priority": "normal"},
    "house_2":  {"base": 0.7, "peak_hour": 20, "peak_mult": 1.9, "priority": "normal"},
    "house_3":  {"base": 1.1, "peak_hour": 18, "peak_mult": 2.1, "priority": "normal"},
    "house_4":  {"base": 0.8, "peak_hour": 21, "peak_mult": 1.7, "priority": "normal"},
    "house_5":  {"base": 1.0, "peak_hour": 19, "peak_mult": 2.0, "priority": "normal"},
    "house_6":  {"base": 0.6, "peak_hour": 20, "peak_mult": 1.8, "priority": "normal"},
    "house_7":  {"base": 0.9, "peak_hour": 18, "peak_mult": 2.3, "priority": "normal"},
    "house_8":  {"base": 1.2, "peak_hour": 21, "peak_mult": 1.6, "priority": "normal"},
    "house_9":  {"base": 0.8, "peak_hour": 19, "peak_mult": 2.0, "priority": "normal"},
    "house_10": {"base": 0.7, "peak_hour": 20, "peak_mult": 1.9, "priority": "normal"},
}


def _gauss(h: int, peak: int, width: float = 3.5) -> float:
    return float(np.exp(-((h - peak) ** 2) / (2 * width ** 2)))


def generate_demand_forecast(house_id: str, hours: int = 24, noise_factor: float = 0.08) -> List[float]:
    p = HOUSE_PROFILES.get(house_id, HOUSE_PROFILES["house_1"])
    base, peak_h, peak_m = p["base"], p["peak_hour"], p["peak_mult"]
    rng = np.random.RandomState(hash(house_id + str(datetime.now().date())) % (2 ** 31))
    out = []
    for h in range(hours):
        morning = _gauss(h, 7, 2.5) * 0.5
        evening = _gauss(h, peak_h, 2.0) * (peak_m - 1.0)
        nf = 0.3 if h < 5 else 1.0
        val = base * (1.0 + morning + evening) * nf
        out.append(max(0.1, round(val + rng.normal(0, noise_factor * val), 3)))
    return out


def generate_solar_forecast(capacity_kw: float = 30.0, cloud_cover: float = None) -> List[float]:
    if cloud_cover is None:
        cloud_cover = np.random.uniform(0.05, 0.4)
    rng = np.random.RandomState(int(datetime.now().toordinal()))
    out = []
    for h in range(24):
        if h < 6 or h > 19:
            out.append(0.0)
        else:
            peak = capacity_kw * (1 - cloud_cover) * _gauss(h, 13, 3.5)
            out.append(max(0.0, round(peak + rng.normal(0, 0.04 * peak), 3)))
    return out


def generate_battery_soc_trajectory(
    initial_soc: float,
    solar: List[float],
    total_demand: List[float],
    capacity_kwh: float = 50.0,
) -> List[float]:
    soc = initial_soc
    traj = []
    for h in range(24):
        net = solar[h] - total_demand[h]
        if net > 0:
            soc += min(net * 0.92, (1.0 - soc) * capacity_kwh) / capacity_kwh
        else:
            soc -= min(abs(net), soc * capacity_kwh * 0.92) / capacity_kwh
        traj.append(round(max(0.05, min(0.98, soc)) * 100, 1))
    return traj


def get_current_stats() -> Dict:
    h = datetime.now().hour
    rng = np.random.RandomState(int(datetime.now().timestamp() / 60))
    solar = generate_solar_forecast(30.0)
    demands = {hid: generate_demand_forecast(hid) for hid in HOUSE_PROFILES}
    total_demand = [sum(demands[hid][i] for hid in HOUSE_PROFILES) for i in range(24)]
    cur_solar = solar[h]
    cur_demand = total_demand[h]
    battery_soc = round(62.5 + rng.normal(0, 2), 1)
    deficit = round(max(0.0, cur_demand - cur_solar), 2)
    surplus = round(max(0.0, cur_solar - cur_demand), 2)
    return {
        "timestamp":        datetime.now().isoformat(),
        "current_solar_kw": round(cur_solar, 2),
        "current_demand_kw":round(cur_demand, 2),
        "battery_soc_pct":  battery_soc,
        "net_energy_kw":    round(cur_solar - cur_demand, 2),
        "deficit_kw":       deficit,
        "surplus_kw":       surplus,
        "active_houses":    len(HOUSE_PROFILES),
        "blackout_risk":    "high" if deficit > 5 else ("medium" if deficit > 2 else "low"),
    }
