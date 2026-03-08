"""
LP Energy Optimizer — PuLP CBC solver.
Priority: clinic > school > pump > households
"""
import logging
from dataclasses import dataclass
from typing import Dict, List

logger = logging.getLogger(__name__)

try:
    import pulp
    PULP_AVAILABLE = True
except ImportError:
    PULP_AVAILABLE = False
    logger.warning("PuLP not installed — greedy fallback active")

PRIORITY_WEIGHTS = {"critical": 1.0, "high": 0.85, "normal": 0.60}
MIN_GUARANTEE    = {"critical": 0.95, "high": 0.80, "normal": 0.50}


@dataclass
class ConsumerProfile:
    consumer_id:       str
    demand_kw:         float
    priority:          str
    min_guarantee_pct: float


def run_optimization(
    consumers: List[ConsumerProfile],
    available_kw: float,
    battery_kw: float = 0.0,
) -> Dict[str, float]:
    total = available_kw + battery_kw
    if total >= sum(c.demand_kw for c in consumers):
        return {c.consumer_id: round(c.demand_kw, 3) for c in consumers}
    if PULP_AVAILABLE:
        try:
            return _lp(consumers, total)
        except Exception as e:
            logger.error(f"LP failed: {e}")
    return _greedy(consumers, total)


def _lp(consumers: List[ConsumerProfile], total: float) -> Dict[str, float]:
    prob  = pulp.LpProblem("Microgrid", pulp.LpMaximize)
    alloc = {c.consumer_id: pulp.LpVariable(f"x_{c.consumer_id}", 0, c.demand_kw) for c in consumers}

    prob += pulp.lpSum(
        PRIORITY_WEIGHTS[c.priority] * alloc[c.consumer_id] / max(c.demand_kw, 0.01)
        for c in consumers
    )
    prob += pulp.lpSum(alloc[c.consumer_id] for c in consumers) <= total

    min_total = sum(MIN_GUARANTEE[c.priority] * c.demand_kw for c in consumers)
    if min_total <= total:
        for c in consumers:
            prob += alloc[c.consumer_id] >= MIN_GUARANTEE[c.priority] * c.demand_kw
    else:
        for c in consumers:
            if c.priority == "critical":
                prob += alloc[c.consumer_id] >= min(0.90 * c.demand_kw, total * 0.25)

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[prob.status] == "Optimal":
        return {c.consumer_id: round(pulp.value(alloc[c.consumer_id]), 3) for c in consumers}
    return _greedy(consumers, total)


def _greedy(consumers: List[ConsumerProfile], total: float) -> Dict[str, float]:
    result    = {c.consumer_id: 0.0 for c in consumers}
    remaining = total
    for c in sorted(consumers, key=lambda x: {"critical": 0, "high": 1, "normal": 2}[x.priority]):
        give = round(min(c.demand_kw, remaining), 3)
        result[c.consumer_id] = max(0.0, give)
        remaining -= give
        if remaining <= 0:
            break
    return result


def compute_fairness_index(allocs: Dict[str, float], demands: Dict[str, float]) -> float:
    sats = [allocs[c] / max(demands.get(c, 1.0), 0.001) for c in allocs]
    if not sats:
        return 1.0
    n, s = len(sats), sum(sats)
    sq   = sum(x ** 2 for x in sats)
    return round((s ** 2) / (n * sq), 4) if sq else 0.0


def compute_unmet_pct(allocs: Dict[str, float], demands: Dict[str, float]) -> float:
    td = sum(demands.values())
    ta = sum(allocs.values())
    return round((1 - ta / td) * 100, 2) if td else 0.0
