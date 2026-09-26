"""
IntelliFlow 2.0 — Decision Engine REST APIs
Handles Impact Simulation, Network Optimization, Anomaly Detection,
Feedback Learning Loop, and Safe Retraining endpoints.
"""

import json
import logging
import numpy as np
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import Intersection
from signals_app.models import (
    SignalState,
    SimulationResult,
    TrafficControlExperience,
    TrafficAnomaly,
    ModelVersion,
)
from signals_app.engine import (
    traffic_simulator,
    network_optimizer,
    anomaly_detector,
    learning_engine,
    network_topology,
)

logger = logging.getLogger("signals_app.api_views")

def _parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return {}

@csrf_exempt
@require_http_methods(["POST"])
def simulate_impact_api(request):
    """
    POST /signals/api/simulate-impact/
    Payload: {
        "intersection_id": "Electronic City::Silk Board Junction",
        "current_green": 45,
        "proposed_green": 60,
        "duration_minutes": 15,
        "connected_ids": ["Koramangala::Sony World Junction"]
    }
    """
    data = _parse_json(request)
    ix_id = data.get("intersection_id")
    if not ix_id:
        return JsonResponse({"error": "intersection_id is required"}, status=400)

    intersection = get_object_or_404(Intersection, intersection_id=ix_id)
    current_green = int(data.get("current_green", intersection.default_green_seconds or 45))
    proposed_green = int(data.get("proposed_green", 60))
    duration_minutes = int(data.get("duration_minutes", 15))
    connected_ids = data.get("connected_ids", [])

    # Run Simulation Engine
    sim_result = traffic_simulator.simulate(
        intersection=intersection,
        current_green=current_green,
        proposed_green=proposed_green,
        duration_minutes=duration_minutes,
        connected_ids=connected_ids,
    )

    # Persist simulation log
    SimulationResult.objects.create(
        intersection=intersection,
        current_green_seconds=current_green,
        proposed_green_seconds=proposed_green,
        simulation_duration_minutes=duration_minutes,
        connected_intersections=connected_ids,
        baseline_metrics=sim_result["baseline_metrics"],
        simulated_metrics=sim_result["simulated_metrics"],
        delta_metrics=sim_result["delta_metrics"],
        network_impact=sim_result["overall_network_impact"],
        data_sources=sim_result["data_sources"],
        ai_explanation=sim_result["ai_explanation"],
    )

    return JsonResponse({"status": "success", "data": sim_result})

@csrf_exempt
@require_http_methods(["POST"])
def optimize_network_api(request):
    """
    POST /signals/api/optimize-network/
    Payload: {
        "intersection_ids": ["Electronic City::Silk Board Junction", ...],
        "corridor_id": "ORR",
        "emergency_priority": true
    }
    """
    data = _parse_json(request)
    intersection_ids = data.get("intersection_ids")
    corridor_id = data.get("corridor_id")
    emergency_priority = bool(data.get("emergency_priority", True))

    opt_result = network_optimizer.optimize_network(
        intersection_ids=intersection_ids,
        corridor_id=corridor_id,
        emergency_priority=emergency_priority,
    )

    return JsonResponse(opt_result)

@require_http_methods(["GET"])
def impact_history_api(request):
    """
    GET /signals/api/impact-history/
    Returns recent simulation results.
    """
    sims = SimulationResult.objects.select_related("intersection").all().order_by("-created_at")[:20]
    results = []
    for s in sims:
        results.append({
            "id": s.id,
            "intersection_id": s.intersection.intersection_id,
            "created_at": s.created_at.isoformat(),
            "current_green_seconds": s.current_green_seconds,
            "proposed_green_seconds": s.proposed_green_seconds,
            "delta_metrics": s.delta_metrics,
            "network_impact": s.network_impact,
            "ai_explanation": s.ai_explanation,
        })
    return JsonResponse({"status": "success", "count": len(results), "simulations": results})

@require_http_methods(["GET"])
def learning_performance_api(request):
    """
    GET /signals/api/learning-performance/
    Returns self-learning history, prediction errors, and model improvement metrics.
    """
    exps = TrafficControlExperience.objects.select_related("intersection").all().order_by("-timestamp")
    total_count = exps.count()
    improved_count = exps.filter(outcome="IMPROVED").count()
    degraded_count = exps.filter(outcome="DEGRADED").count()
    neutral_count = exps.filter(outcome="NEUTRAL").count()

    improvement_rate_pct = round((improved_count / max(total_count, 1)) * 100.0, 1)

    # Average errors
    queue_errors = [abs(e.queue_error) for e in exps if e.queue_error is not None]
    cong_errors = [abs(e.congestion_error) for e in exps if e.congestion_error is not None]
    mean_abs_queue_error = round(float(np.mean(queue_errors)), 2) if queue_errors else 0.0
    mean_abs_cong_error = round(float(np.mean(cong_errors)), 2) if cong_errors else 0.0

    recent_experiences = []
    for e in exps[:25]:
        recent_experiences.append({
            "id": e.id,
            "intersection_id": e.intersection.intersection_id,
            "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M"),
            "previous_green_seconds": e.previous_green_seconds,
            "applied_green_seconds": e.applied_green_seconds,
            "predicted_queue": e.predicted_queue,
            "actual_queue": e.actual_queue,
            "queue_error": e.queue_error,
            "predicted_congestion": e.predicted_congestion,
            "actual_congestion": e.actual_congestion,
            "congestion_error": e.congestion_error,
            "outcome": e.outcome,
            "was_congestion_reduced": e.was_congestion_reduced,
            "operator_notes": e.operator_notes,
            "used_in_retraining": e.used_in_retraining,
        })

    # Active model versions
    versions = []
    for v in ModelVersion.objects.all().order_by("-training_timestamp")[:5]:
        versions.append({
            "version_id": v.version_id,
            "model_type": v.model_type,
            "dataset_size": v.dataset_size,
            "validation_score": v.validation_score,
            "is_active": v.is_active,
            "training_timestamp": v.training_timestamp.strftime("%Y-%m-%d %H:%M"),
        })

    return JsonResponse({
        "status": "success",
        "summary": {
            "total_experiences": total_count,
            "improved_count": improved_count,
            "degraded_count": degraded_count,
            "neutral_count": neutral_count,
            "improvement_rate_pct": improvement_rate_pct,
            "mean_abs_queue_error_vehicles": mean_abs_queue_error,
            "mean_abs_congestion_error": mean_abs_cong_error,
            "learning_status": "ONLINE & CONTINUOUSLY ADAPTING",
        },
        "experiences": recent_experiences,
        "model_versions": versions,
    })

@require_http_methods(["GET"])
def anomalies_api(request):
    """
    GET /signals/api/anomalies/
    Returns real-time detected traffic anomalies across all active intersections.
    """
    active_anomalies = anomaly_detector.scan_all_active()
    persisted = TrafficAnomaly.objects.filter(is_resolved=False).order_by("-detected_at")[:10]

    persisted_list = []
    for a in persisted:
        persisted_list.append({
            "id": a.id,
            "intersection_id": a.intersection.intersection_id,
            "severity": a.severity,
            "anomaly_type": a.anomaly_type,
            "confidence": a.confidence,
            "detected_at": a.detected_at.strftime("%Y-%m-%d %H:%M"),
            "supporting_metrics": a.supporting_metrics,
        })

    return JsonResponse({
        "status": "success",
        "realtime_scanned_count": len(active_anomalies),
        "realtime_anomalies": active_anomalies,
        "active_persisted_anomalies": persisted_list,
    })

@csrf_exempt
@require_http_methods(["POST"])
def apply_feedback_api(request):
    """
    POST /signals/api/feedback/
    Human-in-the-Loop [APPLY]:
    Applies proposed timing to SignalState, records TrafficControlExperience,
    and updates learning bias loop.
    Payload: {
        "intersection_id": "Electronic City::Silk Board Junction",
        "previous_green": 45,
        "applied_green": 60,
        "predicted_metrics": { "queue": 80.0, "congestion": 65.0, "volume": 22000.0, "delay": 48.0 },
        "actual_metrics": { "queue": 68.0, "congestion": 60.5, "volume": 21800.0, "delay": 41.0 }, // optional
        "operator_notes": "Applied recommendation after simulation review"
    }
    """
    data = _parse_json(request)
    ix_id = data.get("intersection_id")
    if not ix_id:
        return JsonResponse({"error": "intersection_id is required"}, status=400)

    intersection = get_object_or_404(Intersection, intersection_id=ix_id)
    applied_green = int(data.get("applied_green", 45))
    previous_green = int(data.get("previous_green", 45))
    predicted_metrics = data.get("predicted_metrics", {})
    actual_metrics = data.get("actual_metrics")
    operator_notes = data.get("operator_notes", "Operator approved AI recommendation via Decision Center.")

    # Safety clamp: [30, 75] seconds
    applied_green = int(np.clip(applied_green, 30, 75))

    # 1. Update physical SignalState in database
    sig, _ = SignalState.objects.get_or_create(intersection=intersection)
    sig.green_duration_seconds = applied_green
    sig.save()

    # 2. Record Experience into Database (Self-Learning Feedback Loop ⭐)
    experience = learning_engine.record_experience(
        intersection=intersection,
        previous_green=previous_green,
        applied_green=applied_green,
        predicted_metrics=predicted_metrics,
        actual_metrics=actual_metrics,
        operator_notes=operator_notes,
    )

    return JsonResponse({
        "status": "success",
        "message": f"Signal updated to {applied_green}s and experience recorded for self-learning.",
        "experience": {
            "id": experience.id,
            "intersection_id": intersection.intersection_id,
            "applied_green_seconds": experience.applied_green_seconds,
            "predicted_queue": experience.predicted_queue,
            "actual_queue": experience.actual_queue,
            "queue_error": experience.queue_error,
            "predicted_congestion": experience.predicted_congestion,
            "actual_congestion": experience.actual_congestion,
            "congestion_error": experience.congestion_error,
            "outcome": experience.outcome,
            "was_congestion_reduced": experience.was_congestion_reduced,
        }
    })

@csrf_exempt
@require_http_methods(["POST"])
def safe_retrain_api(request):
    """
    POST /signals/api/retrain/
    Triggers safe online candidate retraining combining historical dataset
    with new feedback experience.
    """
    data = _parse_json(request)
    min_samples = int(data.get("min_new_samples", 1))

    retrain_result = learning_engine.safe_retrain_pipeline(min_new_samples=min_samples)
    return JsonResponse(retrain_result)
