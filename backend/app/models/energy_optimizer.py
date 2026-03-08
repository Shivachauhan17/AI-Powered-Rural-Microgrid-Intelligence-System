"""
Energy Allocation Optimizer using Linear Programming (PuLP).
Fairly distributes available solar + battery power across all consumers.
Priority: Clinic > School > Pump > Households
"""
import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass

try:
    import pulp
    PULP_AVAILABLE = True
except ImportError:
    PULP_AVAILABLE = False
    logging.warning("PuLP not installed, using greedy fallback optimizer.")

logger = logging.getLogger(__name__)


@dataclass
class ConsumerProfile:
    consumer_id: str
    demand_kw: float
    priority: str          # "critical", "high", "normal"
    min_guarantee_pct: float  # Minimum % of demand guaranteed


PRIORITY_WEIGHTS = {"critical": 1.0, "high": 0.85, "normal": 0.60}
MIN_GUARANTEE = {"critical": 0.95, "high": 0.80, "normal": 0.50}


def run_optimization(
    consumers: List[ConsumerProfile],
    available_energy_kw: float,
    battery_discharge_kw: float = 0.0,
) -> Dict[str, float]:
    """
    Run LP optimization to allocate energy fairly.
    
    Objective: Maximize weighted satisfaction across all consumers.
    Constraints:
      - Total allocation <= available_energy_kw + battery_discharge_kw
      - Each consumer >= min_guarantee_pct * demand (if feasible)
      - Each consumer <= demand (no over-supply)
    """
    total_available = available_energy_kw + battery_discharge_kw
    total_demand = sum(c.demand_kw for c in consumers)
    
    # If enough energy, just allocate full demand
    if total_available >= total_demand:
        return {c.consumer_id: round(c.demand_kw, 3) for c in consumers}
    
    if not PULP_AVAILABLE:
        return _greedy_fallback(consumers, total_available)
    
    try:
        return _lp_optimize(consumers, total_available)
    except Exception as e:
        logger.error(f"LP optimization failed: {e}. Using greedy fallback.")
        return _greedy_fallback(consumers, total_available)


def _lp_optimize(consumers: List[ConsumerProfile], total_available: float) -> Dict[str, float]:
    """PuLP linear programming optimization."""
    prob = pulp.LpProblem("MicrogridEnergyAllocation", pulp.LpMaximize)
    
    # Decision variables: allocation for each consumer (0 to demand)
    alloc = {
        c.consumer_id: pulp.LpVariable(
            f"alloc_{c.consumer_id}",
            lowBound=0,
            upBound=c.demand_kw
        )
        for c in consumers
    }
    
    # Objective: maximize weighted satisfaction
    weights = {c.consumer_id: PRIORITY_WEIGHTS[c.priority] for c in consumers}
    prob += pulp.lpSum(
        weights[c.consumer_id] * (alloc[c.consumer_id] / max(c.demand_kw, 0.01))
        for c in consumers
    )
    
    # Constraint 1: Total allocation <= available energy
    prob += pulp.lpSum(alloc[c.consumer_id] for c in consumers) <= total_available
    
    # Constraint 2: Minimum guarantees (soft - only if feasible)
    min_total = sum(MIN_GUARANTEE[c.priority] * c.demand_kw for c in consumers)
    if min_total <= total_available:
        for c in consumers:
            prob += alloc[c.consumer_id] >= MIN_GUARANTEE[c.priority] * c.demand_kw
    else:
        # Tighter constraints for priority consumers only
        for c in consumers:
            if c.priority == "critical":
                prob += alloc[c.consumer_id] >= min(0.90 * c.demand_kw, total_available * 0.25)
    
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    
    if pulp.LpStatus[prob.status] == "Optimal":
        return {c.consumer_id: round(pulp.value(alloc[c.consumer_id]), 3) for c in consumers}
    else:
        return _greedy_fallback(consumers, total_available)


def _greedy_fallback(consumers: List[ConsumerProfile], total_available: float) -> Dict[str, float]:
    """Greedy priority-based allocation fallback."""
    result = {c.consumer_id: 0.0 for c in consumers}
    remaining = total_available
    
    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "normal": 2}
    sorted_consumers = sorted(consumers, key=lambda c: priority_order[c.priority])
    
    for c in sorted_consumers:
        min_alloc = MIN_GUARANTEE[c.priority] * c.demand_kw
        give = min(c.demand_kw, remaining)
        result[c.consumer_id] = round(max(0, give), 3)
        remaining -= give
        if remaining <= 0:
            break
    
    return result


def compute_fairness_index(allocations: Dict[str, float], demands: Dict[str, float]) -> float:
    """
    Jain's Fairness Index for energy distribution.
    Returns value between 0 (unfair) and 1 (perfectly fair).
    """
    satisfactions = []
    for cid, alloc in allocations.items():
        demand = demands.get(cid, 1.0)
        satisfactions.append(alloc / max(demand, 0.001))
    
    if not satisfactions:
        return 1.0
    
    n = len(satisfactions)
    s = sum(satisfactions)
    sq_sum = sum(x**2 for x in satisfactions)
    
    if sq_sum == 0:
        return 0.0
    
    return round((s ** 2) / (n * sq_sum), 4)


def compute_unmet_demand_pct(allocations: Dict[str, float], demands: Dict[str, float]) -> float:
    """Percentage of total demand that went unmet."""
    total_demand = sum(demands.values())
    total_allocated = sum(allocations.values())
    
    if total_demand == 0:
        return 0.0
    
    return round((1 - total_allocated / total_demand) * 100, 2)
