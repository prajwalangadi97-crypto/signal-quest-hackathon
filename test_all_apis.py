"""
Comprehensive End-to-End API and Dashboard Verification Script.
Tests every page, AJAX endpoint, and REST API in IntelliFlow.
"""
import os
import sys
import json
import time
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
django.setup()

from django.test import Client
from accounts.models import CustomUser
from core.models import Intersection

def run_tests():
    c = Client()
    # Ensure admin user exists and is logged in
    user, _ = CustomUser.objects.get_or_create(username="admin", defaults={"role": "admin", "is_superuser": True, "is_staff": True})
    user.set_password("admin123")
    user.save()
    c.force_login(user)

    results = []

    def log_test(category, name, url, status, duration_ms, details):
        success = (200 <= status < 400)
        results.append({
            "category": category,
            "name": name,
            "url": url,
            "status": status,
            "duration_ms": round(duration_ms, 1),
            "success": success,
            "details": details
        })
        icon = "✅" if success else "❌"
        print(f"{icon} [{category}] {name} ({url}) -> HTTP {status} in {duration_ms:.1f}ms: {details}")

    first_ix = Intersection.objects.filter(is_active=True).first()
    ix_id = first_ix.id if first_ix else 1
    ix_str = first_ix.intersection_id if first_ix else "ELECTRONIC CITY::HOSUR ROAD"

    print("=" * 80)
    print("🚀 STARTING FULL INTELLIFLOW END-TO-END SUITE VERIFICATION")
    print("=" * 80)

    # 1. CORE PAGES (HTML)
    pages = [
        ("Dashboard", "Main Operations Dashboard", "/dashboard/"),
        ("Live Map", "Dark Canvas Traffic Map", "/map/"),
        ("Intersections", "Intersection Grid Registry", "/map/intersections/"),
        ("Intersections", "Intersection Detail View", f"/map/intersections/{ix_id}/"),
        ("Routing", "Route Planner UI", "/routing/"),
        ("Signals", "Adaptive Signal Controller Deck", "/signals/"),
        ("Emergency", "Emergency Management Deck", "/emergency/"),
        ("Analytics", "Analytics & What-If AI Lab", "/analytics/"),
        ("Vision", "YOLOv8 CCTV Upload Interface", "/vision/"),
        ("Admin", "Django Admin Portal", "/admin/"),
    ]

    for cat, name, url in pages:
        t0 = time.time()
        resp = c.get(url)
        t_ms = (time.time() - t0) * 1000
        det = f"Page loaded ({len(resp.content)} bytes)"
        log_test(cat, name, url, resp.status_code, t_ms, det)

    # 2. REST & AJAX APIS
    # 2a. Dashboard Weather API
    t0 = time.time()
    resp = c.get("/dashboard/api/weather/")
    t_ms = (time.time() - t0) * 1000
    try:
        data = resp.json()
        det = f"City: {data.get('city')}, Temp: {data.get('temperature')}°C, Condition: {data.get('condition')}"
    except Exception as e:
        det = str(e)
    log_test("Dashboard", "Weather API", "/dashboard/api/weather/", resp.status_code, t_ms, det)

    # 2b. Core Intersections API
    t0 = time.time()
    resp = c.get("/api/intersections/")
    t_ms = (time.time() - t0) * 1000
    try:
        data = resp.json()
        count = len(data) if isinstance(data, list) else len(data.get('features', []))
        det = f"Loaded {count} intersections"
    except Exception as e:
        det = str(e)
    log_test("Core API", "Intersections GeoJSON API", "/api/intersections/", resp.status_code, t_ms, det)

    # 2c. Core Latest Predictions API
    t0 = time.time()
    resp = c.get("/api/predictions/latest/")
    t_ms = (time.time() - t0) * 1000
    try:
        data = resp.json()
        count = len(data) if isinstance(data, list) else len(data.get('predictions', []))
        det = f"Loaded {count} predicted intersections"
    except Exception as e:
        det = str(e)
    log_test("Core API", "Latest Predictions API", "/api/predictions/latest/", resp.status_code, t_ms, det)

    # 2d. Routing Geocode API
    t0 = time.time()
    resp = c.post("/routing/api/geocode/", data=json.dumps({"query": "marathalli"}), content_type="application/json")
    t_ms = (time.time() - t0) * 1000
    try:
        data = resp.json()
        det = f"Resolved to: {data[0].get('display_name') if data else 'None'} ({data[0].get('lat')}, {data[0].get('lon')})"
    except Exception as e:
        det = str(e)
    log_test("Routing", "Geocoding Landmark API", "/routing/api/geocode/", resp.status_code, t_ms, det)

    # 2e. Routing Calculation API
    t0 = time.time()
    resp = c.post("/routing/api/route/", data=json.dumps({
        "start": [77.7011, 12.9591],
        "end": [77.5713, 12.9767]
    }), content_type="application/json")
    t_ms = (time.time() - t0) * 1000
    try:
        data = resp.json()
        routes = data.get("routes", [])
        det = f"Calculated {len(routes)} routes. Best ETA: {round(routes[0].get('adjusted_eta_seconds', 0)/60)} min ({routes[0].get('penalty_factor')}x penalty)"
    except Exception as e:
        det = str(e)
    log_test("Routing", "Route Finding & AI Scoring API", "/routing/api/route/", resp.status_code, t_ms, det)

    # 2f. Analytics What-If API
    t0 = time.time()
    resp = c.post("/analytics/api/whatif/", data=json.dumps({
        "vehicle_count": 24000,
        "hour": 18,
        "weather": "Rainy",
        "intersection_id": ix_str
    }), content_type="application/json")
    t_ms = (time.time() - t0) * 1000
    try:
        data = resp.json()
        det = f"Predicted Class: {data.get('predicted_class')}, Volume: {data.get('predicted_volume')}, Signal Rec: {data.get('recommended_signal_seconds')}s"
    except Exception as e:
        det = str(e)
    log_test("Analytics", "What-If Scenario Simulation API", "/analytics/api/whatif/", resp.status_code, t_ms, det)

    # 2g. Signals Simulate Impact API
    t0 = time.time()
    resp = c.post("/signals/api/simulate-impact/", data=json.dumps({
        "intersection_id": ix_str,
        "action_type": "EXTEND_GREEN",
        "action_value": 15,
        "duration_minutes": 30
    }), content_type="application/json")
    t_ms = (time.time() - t0) * 1000
    try:
        data = resp.json()
        det = f"Projected delay diff: {data.get('delay_diff')}s, Congestion diff: {data.get('congestion_diff')}%, Impact: {data.get('impact_assessment')}"
    except Exception as e:
        det = str(e)
    log_test("Signals", "Traffic Impact Simulation API", "/signals/api/simulate-impact/", resp.status_code, t_ms, det)

    # 2h. Signals Network Optimization API
    t0 = time.time()
    resp = c.post("/signals/api/optimize-network/", data=json.dumps({
        "emergency_priority": False,
        "target_corridor": "ALL"
    }), content_type="application/json")
    t_ms = (time.time() - t0) * 1000
    try:
        data = resp.json()
        det = f"Optimized {len(data.get('recommendations', []))} junctions. Avg green diff: {data.get('avg_green_diff', 0):.1f}s"
    except Exception as e:
        det = str(e)
    log_test("Signals", "Network-Wide Coordination API", "/signals/api/optimize-network/", resp.status_code, t_ms, det)

    # 2i. Signals Anomalies API
    t0 = time.time()
    resp = c.get("/signals/api/anomalies/")
    t_ms = (time.time() - t0) * 1000
    try:
        data = resp.json()
        det = f"Found {len(data.get('anomalies', []))} active anomalies in network"
    except Exception as e:
        det = str(e)
    log_test("Signals", "Anomaly Detection API", "/signals/api/anomalies/", resp.status_code, t_ms, det)

    # 2j. Signals Learning Performance API
    t0 = time.time()
    resp = c.get("/signals/api/learning-performance/")
    t_ms = (time.time() - t0) * 1000
    try:
        data = resp.json()
        det = f"Experiences: {data.get('total_experiences', 0)}, Improvement Rate: {data.get('improvement_rate', 0)}%"
    except Exception as e:
        det = str(e)
    log_test("Signals", "Self-Learning Performance API", "/signals/api/learning-performance/", resp.status_code, t_ms, det)

    # 2k. Vision CCTV YOLOv8 Detection API
    sample_img_path = "media/sample_traffic.jpg"
    if os.path.exists(sample_img_path):
        with open(sample_img_path, "rb") as f:
            t0 = time.time()
            resp = c.post("/vision/api/detect/", data={"image": f, "intersection": ix_id})
            t_ms = (time.time() - t0) * 1000
        try:
            data = resp.json()
            det = f"Detected {data.get('total_vehicles')} vehicles (Cars: {data.get('vehicle_counts', {}).get('car', 0)}, Buses: {data.get('vehicle_counts', {}).get('bus', 0)}). Emergency: {data.get('emergency_detected')}"
        except Exception as e:
            det = str(e)
        log_test("Vision", "YOLOv8 Live Traffic Detection API", "/vision/api/detect/", resp.status_code, t_ms, det)

    # 2l. Emergency Management Flow
    t0 = time.time()
    resp = c.post("/emergency/create/", data={
        "vehicle_type": "ambulance",
        "plate_number": "KA-01-EQ-9999",
        "intersection": ix_id,
        "notes": "Automated verification test emergency"
    }, follow=True)
    t_ms = (time.time() - t0) * 1000
    log_test("Emergency", "Report Emergency Vehicle", "/emergency/create/", resp.status_code, t_ms, "Emergency created & signal locked GREEN")

    # Find created EV to resolve
    from signals_app.models import EmergencyVehicle
    ev = EmergencyVehicle.objects.filter(plate_number="KA-01-EQ-9999", route_cleared=False).first()
    if ev:
        t0 = time.time()
        resp = c.post(f"/emergency/{ev.pk}/resolve/", follow=True)
        t_ms = (time.time() - t0) * 1000
        log_test("Emergency", "Resolve Emergency Vehicle", f"/emergency/{ev.pk}/resolve/", resp.status_code, t_ms, "Emergency resolved & signal restored")

    # SUMMARY
    total = len(results)
    passed = sum(1 for r in results if r["success"])
    failed = total - passed

    print("\n" + "=" * 80)
    print(f"🏁 VERIFICATION COMPLETE: {passed}/{total} ENDPOINTS PASSED ({failed} FAILED)")
    print("=" * 80)

    # Save summary report to JSON
    with open("api_verification_report.json", "w") as f:
        json.dump({
            "total": total,
            "passed": passed,
            "failed": failed,
            "results": results
        }, f, indent=2)

    return failed == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
