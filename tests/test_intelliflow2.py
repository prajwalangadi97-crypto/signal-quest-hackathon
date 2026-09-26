"""
IntelliFlow 2.0 Automated Verification Test Suite
Tests Impact Simulation, Network Ripple Modeling, Optimization,
Anomaly Detection, Self-Learning Feedback Loop, Safe Retraining, and REST APIs.
"""

import json
import os
from datetime import date
from django.conf import settings
from django.test import Client, TestCase, override_settings

_test_storages = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

from accounts.models import CustomUser
from core.models import Intersection, TrafficData
from signals_app.models import (
    SignalState,
    EmergencyVehicle,
    TrafficControlExperience,
    SimulationResult,
    ModelVersion,
    TrafficAnomaly,
)
from signals_app.engine import (
    network_topology,
    traffic_simulator,
    network_optimizer,
    anomaly_detector,
    learning_engine,
)

@override_settings(STORAGES=_test_storages)
class TestIntelliFlow2Core(TestCase):
    def setUp(self):
        # Create test admin & operator
        self.operator = CustomUser.objects.create_user(
            username="op_test", password="pass123", role="operator"
        )
        self.admin = CustomUser.objects.create_superuser(
            username="admin_test", password="pass123", role="admin"
        )

        # Create two connected test intersections
        self.ix1 = Intersection.objects.create(
            intersection_id="Electronic City::Silk Board Junction",
            area="Electronic City",
            road="Silk Board Junction",
            latitude=12.9172,
            longitude=77.6228,
            default_green_seconds=45,
            hist_mean_volume=22000.0,
            hist_mean_congestion=72.0,
        )
        self.ix2 = Intersection.objects.create(
            intersection_id="Koramangala::Sony World Junction",
            area="Koramangala",
            road="Sony World Junction",
            latitude=12.9345,
            longitude=77.6146,
            default_green_seconds=45,
            hist_mean_volume=19000.0,
            hist_mean_congestion=65.0,
        )

        # Create SignalState records
        self.sig1 = SignalState.objects.create(intersection=self.ix1, green_duration_seconds=45)
        self.sig2 = SignalState.objects.create(intersection=self.ix2, green_duration_seconds=45)

        # Create recent traffic data
        TrafficData.objects.create(
            intersection=self.ix1,
            recorded_date=date(2024, 8, 1),
            vehicle_count=23500.0,
            avg_speed_kph=18.0,
            travel_time_index=1.45,
            congestion_level=75.0,
            capacity_utilization=78.0,
            incident_reports=0.0,
            signal_compliance=82.0,
            source="dataset",
        )
        TrafficData.objects.create(
            intersection=self.ix2,
            recorded_date=date(2024, 8, 1),
            vehicle_count=19200.0,
            avg_speed_kph=21.0,
            travel_time_index=1.30,
            congestion_level=64.0,
            capacity_utilization=68.0,
            incident_reports=0.0,
            signal_compliance=85.0,
            source="dataset",
        )

    def test_impact_simulation_and_attribution(self):
        """Feature 1: Test impact simulator estimates queue, delay, volume and provides explicit attribution."""
        res = traffic_simulator.simulate(
            intersection=self.ix1,
            current_green=45,
            proposed_green=60,
            duration_minutes=15,
        )
        self.assertIn("baseline_metrics", res)
        self.assertIn("simulated_metrics", res)
        self.assertIn("delta_metrics", res)
        self.assertIn("data_sources", res)
        self.assertIn("ai_explanation", res)

        # Check explicit data source attribution
        sources = res["data_sources"]
        self.assertIn("actual_measured_data", sources)
        self.assertIn("ml_prediction", sources)
        self.assertIn("simulation_result", sources)
        self.assertIn("heuristic_estimate", sources)

        # Verify metrics change logically with increased green
        self.assertEqual(res["proposed_green_seconds"], 60)
        self.assertLessEqual(res["simulated_metrics"]["queue_length_vehicles"], res["baseline_metrics"]["queue_length_vehicles"] * 1.05)

    def test_signal_timing_safety_constraints(self):
        """Feature 9: Test that timings outside [30, 75] are safely clamped."""
        res_low = traffic_simulator.simulate(self.ix1, current_green=15, proposed_green=20)
        self.assertEqual(res_low["current_green_seconds"], 30)
        self.assertEqual(res_low["proposed_green_seconds"], 30)

        res_high = traffic_simulator.simulate(self.ix1, current_green=50, proposed_green=95)
        self.assertEqual(res_high["proposed_green_seconds"], 75)

    def test_network_ripple_model(self):
        """Feature 2: Test network ripple calculation, distance attenuation, and spillback detection."""
        ripple = network_topology.calculate_ripple_effect(
            source_id="Electronic City::Silk Board Junction",
            current_green=45,
            proposed_green=60,
        )
        self.assertIn("directly_affected", ripple)
        self.assertIn("secondary_affected", ripple)
        self.assertGreater(len(ripple["directly_affected"]), 0)

        # Check that downstream nodes have congestion deltas
        first_neighbor = ripple["directly_affected"][0]
        self.assertIn("congestion_change_pct", first_neighbor)
        self.assertIn("distance_km", first_neighbor)
        self.assertGreater(first_neighbor["distance_km"], 0.0)

    def test_network_level_signal_optimizer(self):
        """Feature 3: Test constrained multi-intersection network optimization."""
        opt = network_optimizer.optimize_network(
            intersection_ids=[self.ix1.intersection_id, self.ix2.intersection_id],
            emergency_priority=False,
        )
        self.assertEqual(opt["status"], "success")
        self.assertIn("optimized_timings", opt)
        self.assertIn("delay_savings_pct", opt)
        self.assertIn("recommendations", opt)

        # Verify all timings satisfy 30-75s safety constraint
        for ix_id, timing in opt["optimized_timings"].items():
            self.assertGreaterEqual(timing, 30)
            self.assertLessEqual(timing, 75)

    def test_emergency_aware_network_optimization(self):
        """Feature 10: Test emergency vehicle priority in network optimization."""
        # Create active emergency vehicle at Silk Board
        ev = EmergencyVehicle.objects.create(
            vehicle_type="ambulance",
            plate_number="KA-01-AMB-108",
            intersection=self.ix1,
            route_cleared=False,
        )
        opt = network_optimizer.optimize_network(
            intersection_ids=[self.ix1.intersection_id, self.ix2.intersection_id],
            emergency_priority=True,
        )
        # Silk Board must receive maximum green priority (>= 65s)
        self.assertGreaterEqual(opt["optimized_timings"][self.ix1.intersection_id], 65)

    def test_self_learning_feedback_loop(self):
        """Feature 4: Test recording of decisions and error calculation."""
        exp = learning_engine.record_experience(
            intersection=self.ix1,
            previous_green=45,
            applied_green=60,
            predicted_metrics={"queue": 90.0, "congestion": 70.0, "volume": 22000.0, "delay": 48.0},
            actual_metrics={"queue": 74.0, "congestion": 62.0, "volume": 21800.0, "delay": 40.0},
            operator_notes="Unit test experience logging",
        )
        self.assertIsNotNone(exp.id)
        self.assertEqual(exp.queue_error, -16.0)  # 74 - 90
        self.assertEqual(exp.congestion_error, -8.0)  # 62 - 70
        self.assertEqual(exp.outcome, "IMPROVED")
        self.assertTrue(exp.was_congestion_reduced)

    def test_anomaly_detection_engine(self):
        """Feature 7: Test detection of abnormal traffic behavior."""
        # Create an abnormal traffic spike record (3x normal volume)
        TrafficData.objects.create(
            intersection=self.ix2,
            recorded_date=date(2024, 8, 2),
            vehicle_count=55000.0,  # Extreme surge
            avg_speed_kph=6.0,      # Severe choke
            travel_time_index=3.2,
            congestion_level=95.0,
            capacity_utilization=98.0,
            incident_reports=1.0,
            signal_compliance=50.0,
            source="dataset",
        )
        res = anomaly_detector.scan_intersection(self.ix2, persist=False)
        self.assertIsNotNone(res)
        self.assertIn("severity", res)
        self.assertIn(res["severity"], ["HIGH", "CRITICAL"])
        self.assertIn("confidence", res)
        self.assertIn("supporting_metrics", res)

    def test_safe_retraining_pipeline(self):
        """Feature 6: Test safe online candidate retraining and version tracking."""
        # Ensure at least one experience exists
        learning_engine.record_experience(
            intersection=self.ix1,
            previous_green=45,
            applied_green=55,
            predicted_metrics={"queue": 80.0, "congestion": 65.0, "volume": 21000.0, "delay": 45.0},
            actual_metrics={"queue": 72.0, "congestion": 60.0, "volume": 20800.0, "delay": 39.0},
        )
        res = learning_engine.safe_retrain_pipeline(min_new_samples=1)
        self.assertEqual(res["status"], "success")
        self.assertIn("version_id", res)
        self.assertIn("promoted", res)
        self.assertIn("safety_passed", res)

        # Check ModelVersion was created in database
        self.assertTrue(ModelVersion.objects.filter(version_id=res["version_id"]).exists())

    def test_rest_api_endpoints(self):
        """Test all new IntelliFlow 2.0 REST API endpoints."""
        c = Client()
        c.login(username="op_test", password="pass123")

        # 1. POST /signals/api/simulate-impact/
        resp = c.post(
            "/signals/api/simulate-impact/",
            data=json.dumps({
                "intersection_id": self.ix1.intersection_id,
                "current_green": 45,
                "proposed_green": 60,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        json_data = resp.json()
        self.assertEqual(json_data["status"], "success")

        # 2. POST /signals/api/optimize-network/
        resp = c.post(
            "/signals/api/optimize-network/",
            data=json.dumps({"emergency_priority": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

        # 3. GET /signals/api/learning-performance/
        resp = c.get("/signals/api/learning-performance/")
        self.assertEqual(resp.status_code, 200)

        # 4. GET /signals/api/anomalies/
        resp = c.get("/signals/api/anomalies/")
        self.assertEqual(resp.status_code, 200)

        # 5. POST /signals/api/feedback/
        resp = c.post(
            "/signals/api/feedback/",
            data=json.dumps({
                "intersection_id": self.ix1.intersection_id,
                "previous_green": 45,
                "applied_green": 55,
                "predicted_metrics": {"queue": 80.0, "congestion": 65.0},
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.sig1.refresh_from_db()
        self.assertEqual(self.sig1.green_duration_seconds, 55)

        # 6. GET /signals/decision-center/
        resp = c.get("/signals/decision-center/")
        self.assertEqual(resp.status_code, 200)
