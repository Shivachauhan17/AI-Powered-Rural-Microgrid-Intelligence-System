"""
Realistic data generator for Rural Microgrid simulation.
Simulates 10 households + clinic + school + water pump over 24 hours.
"""
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict


HOUSE_PROFILES = {
    "clinic":    {"base": 3.2, "peak_hour": 10, "peak_mult": 1.8, "priority": "critical"},
    "school":    {"base": 2.5, "peak_hour": 11, "peak_mult": 2.0, "priority": "high"},
    "pump":      {"base": 1.8, "peak_hour": 6,  "peak_mult": 2.5, "priority": "high"},
    "house_1":   {"base": 0.9, "peak_hour": 19, "peak_mult": 2.2, "priority": "normal"},
    "house_2":   {"base": 0.7, "peak_hour": 20, "peak_mult": 1.9, "priority": "normal"},
    "house_3":   {"base": 1.1, "peak_hour": 18, "peak_mult": 2.1, "priority": "normal"},
    "house_4":   {"base": 0.8, "peak_hour": 21, "peak_mult": 1.7, "priority": "normal"},
    "house_5":   {"base": 1.0, "peak_hour": 19, "peak_mult": 2.0, "priority": "normal"},
    "house_6":   {"base": 0.6, "peak_hour": 20, "peak_mult": 1.8, "priority": "normal"},
    "house_7":   {"base": 0.9, "peak_hour": 18, "peak_mult": 2.3, "priority": "normal"},
    "house_8":   {"base": 1.2, "peak_hour": 21, "peak_mult": 1.6, "priority": "normal"},
    "house_9":   {"base": 0.8, "peak_hour": 19, "peak_mult": 2.0, "priority": "normal"},
    "house_10":  {"base": 0.7, "peak_hour": 20, "peak_mult": 1.9, "priority": "normal"},
}


def _gaussian(hour: int, peak: int, width: float = 3.5) -> float:
    return np.exp(-((hour - peak) ** 2) / (2 * width ** 2))


def generate_demand_forecast(house_id: str, hours: int = 24, noise_factor: float = 0.08) -> List[float]:
    """Generate realistic hourly demand forecast for a house."""
    profile = HOUSE_PROFILES.get(house_id, HOUSE_PROFILES["house_1"])
    base = profile["base"]
    peak_hour = profile["peak_hour"]
    peak_mult = profile["peak_mult"]
    
    demands = []
    rng = np.random.RandomState(hash(house_id + str(datetime.now().date())) % (2**31))
    
    for h in range(hours):
        # Morning activity
        morning = _gaussian(h, 7, 2.5) * 0.5
        # Evening peak
        evening = _gaussian(h, peak_hour, 2.0) * (peak_mult - 1.0)
        # Nighttime reduction
        night_factor = 0.3 if (h < 5 or h > 23) else 1.0
        
        demand = base * (1.0 + morning + evening) * night_factor
        noise = rng.normal(0, noise_factor * demand)
        demands.append(max(0.1, round(demand + noise, 3)))
    
    return demands


def generate_solar_forecast(capacity_kw: float = 30.0, cloud_cover: float = None) -> List[float]:
    """Generate realistic hourly solar generation forecast."""
    if cloud_cover is None:
        cloud_cover = np.random.uniform(0.05, 0.4)
    
    solar = []
    rng = np.random.RandomState(int(datetime.now().toordinal()))
    
    for h in range(24):
        if h < 6 or h > 19:
            solar.append(0.0)
        else:
            # Bell curve from 6am to 7pm, peak at 1pm
            peak_gen = capacity_kw * (1 - cloud_cover)
            gen = peak_gen * _gaussian(h, 13, 3.5)
            noise = rng.normal(0, 0.04 * gen)
            solar.append(max(0.0, round(gen + noise, 3)))
    
    return solar


def generate_battery_soc_trajectory(
    initial_soc: float,
    solar: List[float],
    total_demand: List[float],
    capacity_kwh: float = 50.0
) -> List[float]:
    """Simulate battery state-of-charge over 24h."""
    soc = initial_soc
    trajectory = []
    efficiency = 0.92  # charge/discharge efficiency
    
    for h in range(24):
        net = solar[h] - total_demand[h]
        if net > 0:  # Charging
            delta = min(net * efficiency, (1.0 - soc) * capacity_kwh)
            soc += delta / capacity_kwh
        else:  # Discharging
            delta = min(abs(net), soc * capacity_kwh * efficiency)
            soc -= delta / capacity_kwh
        
        soc = max(0.05, min(0.98, soc))
        trajectory.append(round(soc * 100, 1))  # as percentage
    
    return trajectory


def get_current_stats() -> Dict:
    """Get simulated current (live) stats."""
    hour = datetime.now().hour
    rng = np.random.RandomState(int(datetime.now().timestamp() / 60))  # Changes every minute
    
    solar = generate_solar_forecast(30.0)
    all_demands = {hid: generate_demand_forecast(hid) for hid in HOUSE_PROFILES}
    total_demand = [sum(all_demands[h][i] for h in HOUSE_PROFILES) for i in range(24)]
    
    current_solar = solar[hour]
    current_demand = total_demand[hour]
    battery_soc = 62.5 + rng.normal(0, 2)  # Simulated current SOC
    
    deficit = max(0, current_demand - current_solar)
    surplus = max(0, current_solar - current_demand)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "current_solar_kw": round(current_solar, 2),
        "current_demand_kw": round(current_demand, 2),
        "battery_soc_pct": round(battery_soc, 1),
        "net_energy_kw": round(current_solar - current_demand, 2),
        "deficit_kw": round(deficit, 2),
        "surplus_kw": round(surplus, 2),
        "active_houses": len(HOUSE_PROFILES),
        "blackout_risk": "high" if deficit > 5 else ("medium" if deficit > 2 else "low"),
    }
