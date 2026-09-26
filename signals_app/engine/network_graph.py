"""
IntelliFlow 2.0 — Network Topology & Ripple Model (Feature 2)
Models urban intersection graph relationships, arterial corridors,
and dynamic traffic wave propagation across Bengaluru arteries.
"""

import math
import logging
from typing import Dict, List, Tuple, Any

logger = logging.getLogger("signals_app.engine.network_graph")

# Curated corridor links between Bengaluru's 16 monitored intersections
# (Node A, Node B, Distance in km, Corridor Name)
BENGALURU_ROAD_GRAPH: List[Tuple[str, str, float, str]] = [
    # Outer Ring Road & Tech Corridor
    ("Electronic City::Hosur Road", "Electronic City::Silk Board Junction", 6.8, "Hosur Road Arterial"),
    ("Electronic City::Silk Board Junction", "Koramangala::Sony World Junction", 4.2, "Silk Board - Koramangala Link"),
    ("Koramangala::Sony World Junction", "Koramangala::Sarjapur Road", 1.8, "Koramangala Inner Arterial"),
    ("Koramangala::Sarjapur Road", "Whitefield::Marathahalli Bridge", 5.8, "Sarjapur - ORR Link"),
    ("Whitefield::Marathahalli Bridge", "Whitefield::ITPL Main Road", 4.6, "Whitefield IT Corridor"),
    
    # Central - Indiranagar - MG Road Corridor
    ("Koramangala::Sarjapur Road", "Indiranagar::100 Feet Road", 5.1, "Intermediate Ring Road"),
    ("Indiranagar::100 Feet Road", "Indiranagar::CMH Road", 1.2, "Indiranagar Spine"),
    ("Indiranagar::CMH Road", "M.G. Road::Trinity Circle", 2.4, "Old Airport Road Approach"),
    ("M.G. Road::Trinity Circle", "M.G. Road::Anil Kumble Circle", 1.5, "MG Road Boulevard"),
    
    # North - Airport Corridor
    ("M.G. Road::Anil Kumble Circle", "Hebbal::Ballari Road", 7.2, "Central - Bellary Highway"),
    ("Hebbal::Ballari Road", "Hebbal::Hebbal Flyover", 1.1, "Hebbal Junction Complex"),
    
    # South - Jayanagar Corridor
    ("Jayanagar::South End Circle", "Jayanagar::Jayanagar 4th Block", 1.4, "Jayanagar Main Arterial"),
    ("Jayanagar::Jayanagar 4th Block", "Electronic City::Silk Board Junction", 4.8, "BTM - Silk Board Connector"),
    ("Jayanagar::South End Circle", "M.G. Road::Anil Kumble Circle", 4.5, "South - Central Link"),
    
    # West - Yeshwanthpur Corridor
    ("Yeshwanthpur::Tumkur Road", "Yeshwanthpur::Yeshwanthpur Circle", 1.6, "Tumkur Highway Spine"),
    ("Yeshwanthpur::Yeshwanthpur Circle", "Hebbal::Hebbal Flyover", 5.4, "North-West Link (ORR)"),
]

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two GPS coordinates."""
    r = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 2)

class NetworkTopologyManager:
    """Manages intersection graph connections and dynamic traffic flow ripple effects."""

    def __init__(self):
        self.adj: Dict[str, List[Dict[str, Any]]] = {}
        self._build_graph()

    def _build_graph(self):
        for u, v, dist, corridor in BENGALURU_ROAD_GRAPH:
            if u not in self.adj:
                self.adj[u] = []
            if v not in self.adj:
                self.adj[v] = []
            self.adj[u].append({"target": v, "distance_km": dist, "corridor": corridor})
            self.adj[v].append({"target": u, "distance_km": dist, "corridor": corridor})

    def get_direct_neighbors(self, intersection_id: str) -> List[Dict[str, Any]]:
        return self.adj.get(intersection_id, [])

    def get_secondary_neighbors(self, intersection_id: str) -> List[Dict[str, Any]]:
        direct = {edge["target"] for edge in self.get_direct_neighbors(intersection_id)}
        secondary = {}
        for d_id in direct:
            for edge in self.get_direct_neighbors(d_id):
                t_id = edge["target"]
                if t_id != intersection_id and t_id not in direct and t_id not in secondary:
                    secondary[t_id] = {
                        "target": t_id,
                        "via": d_id,
                        "distance_km": edge["distance_km"],
                        "corridor": edge["corridor"],
                    }
        return list(secondary.values())

    def calculate_ripple_effect(
        self,
        source_id: str,
        current_green: int,
        proposed_green: int,
        source_volume: float = 18000.0,
        source_occupancy: float = 65.0,
    ) -> Dict[str, Any]:
        """
        Feature 2: Network Ripple Model.
        Calculates how signal timing modification at source propagates through directly
        and secondarily affected intersections.
        """
        delta_g = proposed_green - current_green
        delta_pct = delta_g / max(current_green, 15)

        direct_neighbors = self.get_direct_neighbors(source_id)
        secondary_neighbors = self.get_secondary_neighbors(source_id)

        ripple_direct = []
        ripple_secondary = []
        spillback_detected = False
        spillback_nodes = []

        # 1. Direct Neighbors (1-Hop)
        for n in direct_neighbors:
            dist = n["distance_km"]
            # Distance attenuation factor: e^(-0.35 * d)
            attenuation = math.exp(-0.35 * dist)
            
            # If delta_g > 0, upstream discharges MORE vehicles into downstream node.
            # If downstream is already busy, congestion delta increases!
            # If delta_g < 0, upstream meters traffic, reducing downstream load.
            congestion_change_pct = round((delta_g * 0.75) * attenuation, 2)
            queue_change_veh = round((delta_g * 0.42) * attenuation, 1)
            delay_change_sec = round((delta_g * 0.35) * attenuation, 1)

            # Detect congestion transfer spillback:
            # If we increase green at source by >= 15s and downstream link is short (< 3km),
            # congestion transfers directly into downstream junction!
            is_spillback = delta_g >= 12 and dist <= 3.0
            if is_spillback:
                spillback_detected = True
                spillback_nodes.append(n["target"])

            ripple_direct.append({
                "intersection_id": n["target"],
                "distance_km": dist,
                "corridor": n["corridor"],
                "congestion_change_pct": congestion_change_pct,
                "queue_change_veh": queue_change_veh,
                "delay_change_sec": delay_change_sec,
                "spillback_risk": is_spillback,
                "impact_type": "Direct Inflow (1-Hop)"
            })

        # 2. Secondary Neighbors (2-Hop)
        for s in secondary_neighbors:
            dist = s["distance_km"]
            # Further attenuated: e^(-0.60 * (d + via_dist))
            attenuation = math.exp(-0.55 * (dist + 2.0))
            congestion_change_pct = round((delta_g * 0.35) * attenuation, 2)
            queue_change_veh = round((delta_g * 0.20) * attenuation, 1)
            delay_change_sec = round((delta_g * 0.15) * attenuation, 1)

            ripple_secondary.append({
                "intersection_id": s["target"],
                "via": s["via"],
                "distance_km": dist,
                "corridor": s["corridor"],
                "congestion_change_pct": congestion_change_pct,
                "queue_change_veh": queue_change_veh,
                "delay_change_sec": delay_change_sec,
                "impact_type": "Secondary Wave (2-Hop)"
            })

        # Summary of overall network delta
        avg_direct_congestion_delta = (
            sum(r["congestion_change_pct"] for r in ripple_direct) / len(ripple_direct)
            if ripple_direct else 0.0
        )

        return {
            "source_id": source_id,
            "delta_green_sec": delta_g,
            "directly_affected": ripple_direct,
            "secondary_affected": ripple_secondary,
            "avg_neighbor_congestion_delta_pct": round(avg_direct_congestion_delta, 2),
            "spillback_detected": spillback_detected,
            "spillback_nodes": spillback_nodes,
            "ripple_summary": (
                f"Timing adjustment ({delta_g:+d}s) creates wave of "
                f"{avg_direct_congestion_delta:+.1f}% congestion shift across {len(ripple_direct)} direct neighbors."
                + (" WARNING: Potential downstream queue spillback detected!" if spillback_detected else "")
            )
        }

# Global singleton instance
network_topology = NetworkTopologyManager()
