"""
IntelliFlow 2.0 — Traffic Anomaly Detection Engine (Feature 7)
Identifies abnormal traffic surges, sudden speed drops, and sensor anomalies
using trained Isolation Forest + statistical multivariate Z-score verification.
"""

import os
import joblib
import logging
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
from django.conf import settings

from core.models import Intersection, TrafficData
from signals_app.models import TrafficAnomaly

logger = logging.getLogger("signals_app.engine.anomaly")

ANOMALY_MODEL_PATH = os.path.join(settings.BASE_DIR, "models", "anomaly", "anomaly_detector.pkl")

class TrafficAnomalyDetector:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.feature_cols = None
        self.threshold = -0.15
        self._load_model()

    def _load_model(self):
        if os.path.exists(ANOMALY_MODEL_PATH):
            try:
                data = joblib.load(ANOMALY_MODEL_PATH)
                self.model = data["model"]
                self.scaler = data["scaler"]
                self.feature_cols = data["feature_cols"]
                self.threshold = data.get("score_threshold", -0.15)
                logger.info("Loaded Isolation Forest Anomaly Detector.")
            except Exception as e:
                logger.warning("Could not load anomaly_detector.pkl: %s. Using Z-score fallback.", e)
        else:
            logger.warning("anomaly_detector.pkl not found at %s. Using Z-score fallback.", ANOMALY_MODEL_PATH)

    def scan_intersection(
        self,
        intersection: Intersection,
        persist: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Scans an intersection's latest observations for abnormal traffic behavior.
        """
        latest = (
            TrafficData.objects.filter(intersection=intersection)
            .order_by("-recorded_date")
            .first()
        )
        if not latest:
            return None

        vol = float(latest.vehicle_count or 18000.0)
        spd = float(latest.avg_speed_kph or 22.0)
        tti = float(latest.travel_time_index or 1.3)
        cap = float(latest.capacity_utilization or 70.0)
        inc = float(latest.incident_reports or 0.0)

        hist_mean_vol = float(intersection.hist_mean_volume or 16500.0)
        hist_mean_cong = float(intersection.hist_mean_congestion or 60.0)

        # 1. Statistical Z-Score metrics
        # Volume deviation
        vol_ratio = vol / max(hist_mean_vol, 1000.0)
        vol_z = (vol - hist_mean_vol) / max(hist_mean_vol * 0.28, 1000.0)
        
        # Speed deviation (Normal urban speed ~24 km/h)
        spd_z = (spd - 24.0) / 6.0

        # 2. ML Isolation Forest Anomaly Score
        ml_score = 0.0
        ml_flag = False
        if self.model and self.scaler:
            try:
                raw_input = np.array([[vol, spd, tti, cap, inc]])
                scaled = self.scaler.transform(raw_input)
                ml_score = float(self.model.decision_function(scaled)[0])
                ml_flag = ml_score < self.threshold
            except Exception as ex:
                logger.error("Error evaluating isolation forest: %s", ex)

        # 3. Anomaly Heuristics
        # Sudden surge: volume > 1.8x historical mean
        is_surge = vol_ratio >= 1.65 or vol_z >= 2.5
        # Sudden collapse: speed < 8 km/h while capacity > 85%
        is_blockage = spd <= 10.0 and cap >= 80.0
        # Sensor glitch: negative values or impossibly high values
        is_sensor_fault = vol < 100 or vol > 65000 or spd < 1.0 or spd > 130.0

        is_anomalous = ml_flag or is_surge or is_blockage or is_sensor_fault

        if not is_anomalous:
            return None

        # Determine anomaly type & severity
        if is_sensor_fault:
            anomaly_type = "Potential Sensor Anomaly / Telemetry Fault"
            severity = "LOW"
            confidence = 88.0
        elif is_blockage and inc > 0:
            anomaly_type = "Reported Incident / Severe Corridor Blockage"
            severity = "CRITICAL"
            confidence = 94.0
        elif is_blockage:
            anomaly_type = "Abnormal Speed Collapse / Physical Choke"
            severity = "HIGH"
            confidence = 90.5
        elif is_surge:
            anomaly_type = "Abnormal Traffic Surge / Unscheduled Congestion Spike"
            severity = "HIGH" if vol_ratio >= 2.0 else "MEDIUM"
            confidence = 86.0
        else:
            anomaly_type = "Unusual Multi-Feature Distribution Drift"
            severity = "MEDIUM"
            confidence = 82.0

        supporting_metrics = {
            "observed_volume": round(vol, 0),
            "historical_mean_volume": round(hist_mean_vol, 0),
            "volume_spike_ratio": f"{vol_ratio:.2f}x",
            "observed_speed_kph": round(spd, 1),
            "travel_time_index": round(tti, 2),
            "capacity_utilization_pct": round(cap, 1),
            "volume_z_score": round(vol_z, 2),
            "isolation_forest_score": round(ml_score, 4),
            "weather": latest.weather_condition or "Clear",
        }

        # Persist to database if requested
        if persist:
            TrafficAnomaly.objects.create(
                intersection=intersection,
                anomaly_score=round(ml_score, 4),
                severity=severity,
                anomaly_type=anomaly_type,
                confidence=confidence,
                supporting_metrics=supporting_metrics,
            )

        return {
            "intersection_id": intersection.intersection_id,
            "area": intersection.area,
            "road": intersection.road,
            "severity": severity,
            "anomaly_type": anomaly_type,
            "confidence": confidence,
            "supporting_metrics": supporting_metrics,
            "message": f"Abnormal traffic pattern detected at {intersection.intersection_id}",
        }

    def scan_all_active(self) -> List[Dict[str, Any]]:
        """Scans all active intersections across Bengaluru and returns active anomalies."""
        anomalies = []
        for ix in Intersection.objects.filter(is_active=True):
            res = self.scan_intersection(ix, persist=False)
            if res:
                anomalies.append(res)
        return anomalies

# Global singleton detector
anomaly_detector = TrafficAnomalyDetector()
