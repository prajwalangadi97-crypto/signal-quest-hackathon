"""
Seeds initial baseline ModelVersion, TrafficControlExperience, and TrafficAnomaly records.
"""

import os
import django
import json
from datetime import datetime, timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.models import Intersection
from signals_app.models import ModelVersion, TrafficControlExperience, TrafficAnomaly
from signals_app.engine import anomaly_detector

def seed():
    print("Seeding IntelliFlow 2.0 initial records...")
    
    # 1. Seed ModelVersion from intelliflow2_metadata.json
    meta_path = os.path.join("metadata", "intelliflow2_metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
            
        for m_name, m_info in meta.get("models", {}).items():
            if not ModelVersion.objects.filter(version_id=f"v2.0-{m_name}").exists():
                ModelVersion.objects.create(
                    version_id=f"v2.0-{m_name}",
                    model_type=m_name,
                    file_path=m_info.get("path", ""),
                    dataset_size=8936,
                    features=m_info.get("features", []),
                    metrics=m_info.get("metrics", {}),
                    validation_score=0.995 if "impact" in m_name else 0.987 if "ripple" in m_name else 0.95,
                    is_active=True,
                )
                print(f"Created ModelVersion: v2.0-{m_name}")

    # 2. Seed realistic TrafficControlExperience records
    sb = Intersection.objects.filter(intersection_id__icontains="Silk Board").first()
    ec = Intersection.objects.filter(intersection_id__icontains="Hosur").first()
    hebbal = Intersection.objects.filter(intersection_id__icontains="Hebbal").first()
    indir = Intersection.objects.filter(intersection_id__icontains="100 Feet").first()
    
    sample_experiences = [
        {
            "intersection": sb or Intersection.objects.first(),
            "prev": 45, "applied": 60,
            "pred_v": 24500, "pred_c": 74.0, "pred_q": 115.0, "pred_d": 58.0,
            "act_v": 24200, "act_c": 71.5, "act_q": 96.0, "act_d": 49.2,
            "notes": "Evening peak surge relief. Operator increased green to 60s."
        },
        {
            "intersection": hebbal or Intersection.objects.all()[1],
            "prev": 50, "applied": 65,
            "pred_v": 28000, "pred_c": 82.0, "pred_q": 138.0, "pred_d": 66.0,
            "act_v": 28450, "act_c": 78.0, "act_q": 118.0, "act_d": 56.5,
            "notes": "Hebbal flyover airport-bound platoon clearance."
        },
        {
            "intersection": indir or Intersection.objects.all()[2],
            "prev": 45, "applied": 50,
            "pred_v": 16200, "pred_c": 58.0, "pred_q": 65.0, "pred_d": 36.0,
            "act_v": 16050, "act_c": 54.0, "act_q": 55.0, "act_d": 31.0,
            "notes": "100 Feet Road weekend retail traffic stabilization."
        },
        {
            "intersection": ec or Intersection.objects.all()[3],
            "prev": 55, "applied": 60,
            "pred_v": 21000, "pred_c": 68.0, "pred_q": 88.0, "pred_d": 44.0,
            "act_v": 20800, "act_c": 64.0, "act_q": 76.0, "act_d": 38.0,
            "notes": "Electronic City morning IT employee commute optimization."
        },
    ]

    for exp in sample_experiences:
        if exp["intersection"]:
            tce = TrafficControlExperience.objects.create(
                intersection=exp["intersection"],
                previous_green_seconds=exp["prev"],
                applied_green_seconds=exp["applied"],
                predicted_volume=exp["pred_v"],
                predicted_congestion=exp["pred_c"],
                predicted_queue=exp["pred_q"],
                predicted_delay=exp["pred_d"],
                actual_volume=exp["act_v"],
                actual_congestion=exp["act_c"],
                actual_queue=exp["act_q"],
                actual_delay=exp["act_d"],
                operator_notes=exp["notes"],
            )
            tce.calculate_errors()
            tce.save()
            print(f"Created Experience: {tce}")

    # 3. Seed initial TrafficAnomaly records
    anomalies = anomaly_detector.scan_all_active()
    for anom in anomalies[:3]:
        ix = Intersection.objects.filter(intersection_id=anom["intersection_id"]).first()
        if ix and not TrafficAnomaly.objects.filter(intersection=ix).exists():
            TrafficAnomaly.objects.create(
                intersection=ix,
                anomaly_score=anom["supporting_metrics"].get("isolation_forest_score", -0.18),
                severity=anom["severity"],
                anomaly_type=anom["anomaly_type"],
                confidence=anom["confidence"],
                supporting_metrics=anom["supporting_metrics"],
            )
            print(f"Created Anomaly record for {ix.intersection_id}")

    print("IntelliFlow 2.0 seeding complete.")

if __name__ == "__main__":
    seed()
