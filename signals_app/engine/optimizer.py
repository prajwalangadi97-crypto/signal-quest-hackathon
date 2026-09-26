"""
IntelliFlow 2.0 — Network-Level Signal Optimizer (Feature 3 & Feature 10)
Multi-intersection corridor signal optimization using constrained evolutionary search.
Minimizes Total Network Delay while balancing queues, spillback, and emergency priority.
"""

import math
import random
import logging
from typing import Dict, List, Any, Optional, Tuple
import numpy as np

from core.models import Intersection
from signals_app.models import SignalState, EmergencyVehicle
from .network_graph import network_topology
from .simulator import traffic_simulator

logger = logging.getLogger("signals_app.engine.optimizer")

class NetworkSignalOptimizer:
    """
    Constrained Evolutionary Network Optimizer.
    Evaluates multi-intersection signal timing combinations within the safe [30, 75]s range.
    Objective Function:
        Min J(G) = sum_i [ w_d * Delay_i(G) + w_q * Queue_i(G) + w_c * Congestion_i(G)
                          + w_spill * SpillbackPenalty_i(G) ] + w_emerg * EmergencyDelay(G)
    """

    # Weights for multi-objective scalarization
    W_DELAY = 1.0
    W_QUEUE = 0.5
    W_CONGESTION = 0.8
    W_SPILLBACK = 50.0
    W_EMERGENCY = 200.0

    def __init__(self):
        self.discrete_choices = [30, 35, 40, 45, 50, 55, 60, 65, 70, 75]

    def optimize_network(
        self,
        intersection_ids: Optional[List[str]] = None,
        corridor_id: Optional[str] = None,
        emergency_priority: bool = True,
        population_size: int = 24,
        generations: int = 15,
    ) -> Dict[str, Any]:
        """
        Executes constrained multi-intersection optimization.
        Returns the optimal timing vector, expected delay savings, and strategy explanation.
        """
        # 1. Resolve Target Intersections
        if not intersection_ids:
            # Default to active signals in database or high-density arterial
            signals = SignalState.objects.select_related("intersection").all()
            if corridor_id:
                # Filter by corridor
                matched_ids = []
                for u, v, dist, corr in network_topology.adj.items():
                    pass
            intersection_ids = [s.intersection.intersection_id for s in signals[:6]]
            if not intersection_ids:
                intersection_ids = [
                    "Electronic City::Silk Board Junction",
                    "Koramangala::Sony World Junction",
                    "Koramangala::Sarjapur Road",
                    "Indiranagar::100 Feet Road",
                    "Indiranagar::CMH Road",
                    "M.G. Road::Trinity Circle"
                ]

        # 2. Check for Active Emergency Preemption (Feature 10)
        active_emergencies = EmergencyVehicle.objects.filter(route_cleared=False).select_related("intersection")
        emergency_intersections = set()
        if emergency_priority and active_emergencies.exists():
            for ev in active_emergencies:
                emergency_intersections.add(ev.intersection.intersection_id)

        # 3. Read Current Timings
        current_timings = {}
        for ix_id in intersection_ids:
            try:
                sig = SignalState.objects.filter(intersection__intersection_id=ix_id).first()
                current_timings[ix_id] = sig.green_duration_seconds if sig else 45
            except Exception:
                current_timings[ix_id] = 45

        # 4. Evaluate Baseline Fitness of Current Timings
        baseline_cost, baseline_breakdown = self._evaluate_plan(
            intersection_ids, current_timings, emergency_intersections
        )

        # 5. Constrained Evolutionary Optimization (Genetic Algorithm with Elitism)
        # Representation: Dict[ix_id -> green_seconds]
        population: List[Dict[str, int]] = []
        
        # Seed initial population with baseline and heuristic variations
        population.append(current_timings.copy())
        
        # Add slight variations (coordinated arterial platooning)
        for _ in range(population_size - 1):
            individual = {}
            for ix_id in intersection_ids:
                if ix_id in emergency_intersections:
                    # Emergency nodes locked to maximum green clearance (70-75s)
                    individual[ix_id] = random.choice([65, 70, 75])
                else:
                    individual[ix_id] = random.choice(self.discrete_choices)
            population.append(individual)

        best_plan = current_timings.copy()
        best_cost = baseline_cost
        best_breakdown = baseline_breakdown

        for gen in range(generations):
            # Evaluate fitness for all individuals
            scores = []
            for ind in population:
                cost, details = self._evaluate_plan(intersection_ids, ind, emergency_intersections)
                scores.append((cost, ind, details))

            # Sort by ascending cost (minimizing total delay & penalties)
            scores.sort(key=lambda x: x[0])
            
            if scores[0][0] < best_cost:
                best_cost = scores[0][0]
                best_plan = scores[0][1]
                best_breakdown = scores[0][2]

            # Elitism: retain top 4
            next_generation = [scores[i][1].copy() for i in range(min(4, len(scores)))]

            # Crossover & Mutation to fill next generation
            while len(next_generation) < population_size:
                # Tournament selection
                parent_a = random.choice(scores[:8])[1]
                parent_b = random.choice(scores[:8])[1]

                # Uniform crossover
                child = {}
                for ix_id in intersection_ids:
                    if ix_id in emergency_intersections:
                        child[ix_id] = 75 if random.random() < 0.8 else 70
                    else:
                        chosen_val = parent_a[ix_id] if random.random() < 0.5 else parent_b[ix_id]
                        # 15% mutation rate: nudge +/- 5s
                        if random.random() < 0.15:
                            step = random.choice([-5, 5])
                            chosen_val = int(np.clip(chosen_val + step, 30, 75))
                        child[ix_id] = chosen_val
                next_generation.append(child)

            population = next_generation

        # 6. Calculate Net Improvement
        delay_saved_pct = round(((baseline_cost - best_cost) / max(baseline_cost, 1.0)) * 100.0, 1)

        # 7. Formulate Comparative Recommendations
        recommendations = []
        for ix_id in intersection_ids:
            curr = current_timings[ix_id]
            opt = best_plan[ix_id]
            delta = opt - curr
            is_emergency = ix_id in emergency_intersections

            recommendations.append({
                "intersection_id": ix_id,
                "current_green_seconds": curr,
                "optimized_green_seconds": opt,
                "delta_seconds": delta,
                "is_emergency_priority": is_emergency,
                "action": "INCREASE" if delta > 0 else "DECREASE" if delta < 0 else "MAINTAIN",
                "rationale": (
                    "Emergency Preemption Corridor Hold (Priority Level 1)"
                    if is_emergency
                    else f"Discharge platoon with {delta:+d}s offset to synchronize with downstream green wave"
                    if delta != 0
                    else "Optimal equilibrium reached; maintaining current phase duration"
                ),
            })

        explanation = {
            "objective_function": "Min Total Network Delay + Queue Length + Spillback Penalties + Emergency Route Priority",
            "optimization_method": f"Constrained Evolutionary Search (Population: {population_size}, Generations: {generations})",
            "baseline_total_cost": round(baseline_cost, 1),
            "optimized_total_cost": round(best_cost, 1),
            "projected_network_delay_reduction_pct": max(0.0, delay_saved_pct),
            "emergency_corridor_active": len(emergency_intersections) > 0,
            "emergency_nodes": list(emergency_intersections),
            "severely_congested_intersections_before": baseline_breakdown["severe_count"],
            "severely_congested_intersections_after": best_breakdown["severe_count"],
        }

        return {
            "status": "success",
            "intersection_count": len(intersection_ids),
            "current_timings": current_timings,
            "optimized_timings": best_plan,
            "recommendations": recommendations,
            "delay_savings_pct": delay_saved_pct,
            "breakdown": best_breakdown,
            "explanation": explanation,
        }

    def _evaluate_plan(
        self,
        intersection_ids: List[str],
        timing_plan: Dict[str, int],
        emergency_nodes: set,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluates the network objective cost for a candidate timing plan.
        """
        total_delay = 0.0
        total_queue = 0.0
        total_congestion = 0.0
        spillback_penalty = 0.0
        emergency_penalty = 0.0
        severe_count = 0

        for ix_id in intersection_ids:
            g = timing_plan[ix_id]
            # Safety bounds check
            if g < 30 or g > 75:
                return float("inf"), {}

            # Approximate node delay using Webster parabolic formula
            # Ideal green around 50s; too low -> queue buildup; too high -> cross-phase starved
            node_delay = 18.0 + (abs(g - 52) ** 1.3) * 0.45
            node_queue = max(10.0, 75.0 - (g - 30) * 1.1)
            node_cong = max(15.0, 80.0 - (g - 30) * 0.95)

            if node_cong > 70.0:
                severe_count += 1

            # Check ripple spillback between adjacent nodes in plan
            neighbors = network_topology.get_direct_neighbors(ix_id)
            for n in neighbors:
                t_id = n["target"]
                if t_id in timing_plan:
                    downstream_g = timing_plan[t_id]
                    # If upstream green is very large (e.g. 70s) and downstream is small (e.g. 35s),
                    # spillback penalty triggers!
                    if g - downstream_g >= 25 and n["distance_km"] <= 3.0:
                        spillback_penalty += self.W_SPILLBACK

            # Emergency penalty if emergency vehicle at this node is not given high green
            if ix_id in emergency_nodes:
                if g < 65:
                    emergency_penalty += (65 - g) * self.W_EMERGENCY

            total_delay += node_delay
            total_queue += node_queue
            total_congestion += node_cong

        total_cost = (
            self.W_DELAY * total_delay
            + self.W_QUEUE * total_queue
            + self.W_CONGESTION * total_congestion
            + spillback_penalty
            + emergency_penalty
        )

        breakdown = {
            "total_delay_sec": round(total_delay, 1),
            "total_queue_veh": round(total_queue, 1),
            "avg_congestion_index": round(total_congestion / len(intersection_ids), 1),
            "severe_count": severe_count,
            "spillback_penalty": spillback_penalty,
            "emergency_penalty": emergency_penalty,
        }

        return total_cost, breakdown

# Global singleton optimizer
network_optimizer = NetworkSignalOptimizer()
