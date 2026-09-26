import json
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from core.models import Intersection, SystemLog
from prediction.models import Prediction
from realtime.broadcast import broadcast_emergency

from .models import EmergencyVehicle, SignalState


@login_required
def signals_list(request):
    latest_pred = Prediction.objects.order_by("-target_date").first()
    target = latest_pred.target_date if latest_pred else date.today() + timedelta(days=1)
    signals = SignalState.objects.select_related("intersection").all()
    preds = {
        p.intersection_id: p
        for p in Prediction.objects.filter(target_date=target)
    }

    items = []
    for sig in signals:
        pred = preds.get(sig.intersection_id)
        rec_green = None
        pred_class = None
        if pred:
            rec_green = pred.recommended_signal_seconds
            if pred.class_probabilities:
                pred_class = pred.class_probabilities.get("predicted_class")

        delta = None
        if rec_green is not None:
            delta = rec_green - sig.green_duration_seconds

        items.append({
            "signal": sig,
            "recommended_green": rec_green,
            "predicted_class": pred_class,
            "delta": delta,
        })

    return render(request, "signals_app/signals_list.html", {"items": items})


@login_required
def signal_override(request, pk):
    sig = get_object_or_404(SignalState, pk=pk)
    if request.method == "POST":
        new_duration = request.POST.get("green_duration")
        reason = request.POST.get("reason", "")
        if new_duration:
            old = sig.green_duration_seconds
            sig.green_duration_seconds = int(new_duration)
            sig.save()
            SystemLog.objects.create(
                level="INFO",
                module="signals",
                message=f"Manual override: {sig.intersection.intersection_id} "
                        f"green {old}s → {new_duration}s",
                context={"reason": reason, "user": request.user.username},
            )
            messages.success(request, f"Signal updated to {new_duration}s.")
    return redirect("signals_app:signals_list")


@login_required
def emergency_list(request):
    active = EmergencyVehicle.objects.filter(route_cleared=False).select_related("intersection")
    resolved = EmergencyVehicle.objects.filter(route_cleared=True).select_related("intersection").order_by("-resolved_at")[:20]
    intersections = Intersection.objects.filter(is_active=True)
    return render(request, "signals_app/emergency_list.html", {
        "active": active,
        "resolved": resolved,
        "intersections": intersections,
    })


@login_required
def emergency_create(request):
    if request.method == "POST":
        vehicle_type = request.POST.get("vehicle_type")
        plate = request.POST.get("plate_number", "")
        ix_id = request.POST.get("intersection")
        notes = request.POST.get("notes", "")

        intersection = get_object_or_404(Intersection, pk=ix_id)
        ev = EmergencyVehicle.objects.create(
            vehicle_type=vehicle_type,
            plate_number=plate,
            intersection=intersection,
            notes=notes,
        )

        # Set emergency override on signal
        try:
            sig = intersection.signal_state
            sig.is_emergency_override = True
            sig.current_state = "green"
            sig.save()
        except SignalState.DoesNotExist:
            pass

        SystemLog.objects.create(
            level="WARNING",
            module="emergency",
            message=f"Emergency vehicle ({vehicle_type}) reported at {intersection.intersection_id}",
            context={"plate": plate, "user": request.user.username},
        )

        # Broadcast via WebSocket
        broadcast_emergency({
            "intersection_id": intersection.intersection_id,
            "lat": intersection.latitude,
            "lng": intersection.longitude,
            "vehicle_type": vehicle_type,
            "is_emergency": True,
        })

        messages.success(request, "Emergency reported and broadcast.")
    return redirect("emergency:emergency_list")


@login_required
def emergency_resolve(request, pk):
    ev = get_object_or_404(EmergencyVehicle, pk=pk)
    if request.method == "POST":
        ev.route_cleared = True
        ev.resolved_at = timezone.now()
        ev.save()

        # Clear emergency override
        try:
            sig = ev.intersection.signal_state
            # Only clear if no other active emergencies at this intersection
            other_active = EmergencyVehicle.objects.filter(
                intersection=ev.intersection, route_cleared=False
            ).exclude(pk=ev.pk).exists()
            if not other_active:
                sig.is_emergency_override = False
                sig.save()
        except SignalState.DoesNotExist:
            pass

        SystemLog.objects.create(
            level="INFO",
            module="emergency",
            message=f"Emergency resolved at {ev.intersection.intersection_id}",
            context={"vehicle_type": ev.vehicle_type, "user": request.user.username},
        )

        broadcast_emergency({
            "intersection_id": ev.intersection.intersection_id,
            "lat": ev.intersection.latitude,
            "lng": ev.intersection.longitude,
            "is_emergency": False,
            "resolved": True,
        })

        messages.success(request, "Emergency resolved.")
    return redirect("emergency:emergency_list")


@login_required
def decision_center_view(request):
    """
    IntelliFlow 2.0 — Predictive Traffic Decision Center.
    Interactive UI for Traffic Impact Simulation, Network Optimization,
    Human-in-the-Loop Approval, and Self-Learning Feedback loop.
    """
    from .models import TrafficControlExperience, SimulationResult, TrafficAnomaly, ModelVersion
    from .engine import network_topology, anomaly_detector

    intersections = Intersection.objects.filter(is_active=True).order_by("area", "road")
    signals = {s.intersection_id: s for s in SignalState.objects.select_related("intersection").all()}
    
    # Pack intersections with their current signal timing
    ix_data = []
    for ix in intersections:
        sig = signals.get(ix.id)
        current_g = sig.green_duration_seconds if sig else ix.default_green_seconds or 45
        ix_data.append({
            "id": ix.id,
            "intersection_id": ix.intersection_id,
            "area": ix.area,
            "road": ix.road,
            "latitude": ix.latitude,
            "longitude": ix.longitude,
            "current_green": current_g,
            "hist_mean_volume": ix.hist_mean_volume or 17000,
            "hist_mean_congestion": ix.hist_mean_congestion or 60,
        })

    recent_experiences = TrafficControlExperience.objects.select_related("intersection").all().order_by("-timestamp")[:15]
    total_exp_count = TrafficControlExperience.objects.count()
    improved_count = TrafficControlExperience.objects.filter(outcome="IMPROVED").count()
    improvement_rate = round((improved_count / max(total_exp_count, 1)) * 100.0, 1)

    active_anomalies = TrafficAnomaly.objects.filter(is_resolved=False).order_by("-detected_at")[:6]
    model_versions = ModelVersion.objects.all().order_by("-training_timestamp")[:4]

    # Pre-select Silk Board for judge demo
    default_ix = (
        intersections.filter(intersection_id__icontains="Silk Board").first()
        or intersections.first()
    )

    return render(request, "signals_app/decision_center.html", {
        "intersections": intersections,
        "ix_data_json": json.dumps(ix_data),
        "default_ix": default_ix,
        "recent_experiences": recent_experiences,
        "total_exp_count": total_exp_count,
        "improved_count": improved_count,
        "improvement_rate": improvement_rate,
        "active_anomalies": active_anomalies,
        "model_versions": model_versions,
    })

