from django.db import models

from core.models import Intersection


class SignalState(models.Model):
    STATE_CHOICES = [
        ("red", "Red"),
        ("yellow", "Yellow"),
        ("green", "Green"),
    ]
    intersection = models.OneToOneField(
        Intersection, on_delete=models.CASCADE, related_name="signal_state"
    )
    current_state = models.CharField(
        max_length=10, choices=STATE_CHOICES, default="green"
    )
    green_duration_seconds = models.IntegerField(default=45)
    is_emergency_override = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Signal state"
        verbose_name_plural = "Signal states"

    def __str__(self):
        return f"Signal: {self.intersection_id} [{self.current_state}]"


class EmergencyVehicle(models.Model):
    VEHICLE_TYPES = [
        ("ambulance", "Ambulance"),
        ("fire", "Fire Engine"),
        ("police", "Police"),
        ("other", "Other"),
    ]
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPES)
    plate_number = models.CharField(max_length=20, blank=True, default="")
    intersection = models.ForeignKey(
        Intersection, on_delete=models.CASCADE, related_name="emergency_vehicles"
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    route_cleared = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self):
        return f"{self.vehicle_type} @ {self.intersection_id} ({self.detected_at})"


class TrafficControlExperience(models.Model):
    """
    Self-Learning Feedback Loop (Feature 4).
    Records decisions made by operators, predictions made by AI, and observed outcomes.
    """
    OUTCOME_CHOICES = [
        ("IMPROVED", "Improved"),
        ("DEGRADED", "Degraded"),
        ("NEUTRAL", "Neutral"),
    ]

    intersection = models.ForeignKey(
        Intersection, on_delete=models.CASCADE, related_name="control_experiences"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    previous_green_seconds = models.IntegerField(default=45)
    applied_green_seconds = models.IntegerField()
    
    # Predicted Metrics before change
    predicted_volume = models.FloatField(null=True, blank=True)
    predicted_congestion = models.FloatField(null=True, blank=True)
    predicted_queue = models.FloatField(null=True, blank=True)
    predicted_delay = models.FloatField(null=True, blank=True)

    # Actual Observed Metrics after change
    actual_volume = models.FloatField(null=True, blank=True)
    actual_congestion = models.FloatField(null=True, blank=True)
    actual_queue = models.FloatField(null=True, blank=True)
    actual_delay = models.FloatField(null=True, blank=True)

    # Prediction Errors (Actual - Predicted)
    volume_error = models.FloatField(null=True, blank=True)
    congestion_error = models.FloatField(null=True, blank=True)
    queue_error = models.FloatField(null=True, blank=True)
    delay_error = models.FloatField(null=True, blank=True)

    # Outcome evaluation
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, default="IMPROVED")
    was_congestion_reduced = models.BooleanField(default=True)
    operator_notes = models.TextField(blank=True, default="")
    used_in_retraining = models.BooleanField(default=False)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Traffic Control Experience"
        verbose_name_plural = "Traffic Control Experiences"

    def __str__(self):
        return f"Experience: {self.intersection_id} ({self.previous_green_seconds}s -> {self.applied_green_seconds}s) [{self.outcome}]"

    def calculate_errors(self):
        if self.actual_volume is not None and self.predicted_volume is not None:
            self.volume_error = round(self.actual_volume - self.predicted_volume, 2)
        if self.actual_congestion is not None and self.predicted_congestion is not None:
            self.congestion_error = round(self.actual_congestion - self.predicted_congestion, 2)
        if self.actual_queue is not None and self.predicted_queue is not None:
            self.queue_error = round(self.actual_queue - self.predicted_queue, 2)
        if self.actual_delay is not None and self.predicted_delay is not None:
            self.delay_error = round(self.actual_delay - self.predicted_delay, 2)

        # Determine outcome
        if self.actual_congestion is not None and self.predicted_congestion is not None:
            if self.actual_congestion < self.predicted_congestion - 1.0:
                self.outcome = "IMPROVED"
                self.was_congestion_reduced = True
            elif self.actual_congestion > self.predicted_congestion + 3.0:
                self.outcome = "DEGRADED"
                self.was_congestion_reduced = False
            else:
                self.outcome = "NEUTRAL"
                self.was_congestion_reduced = True


class SimulationResult(models.Model):
    """
    Traffic Impact Simulation Storage (Feature 1).
    Stores simulated control evaluations, before/after states, and ripple effects.
    """
    intersection = models.ForeignKey(
        Intersection, on_delete=models.CASCADE, related_name="simulations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    current_green_seconds = models.IntegerField()
    proposed_green_seconds = models.IntegerField()
    simulation_duration_minutes = models.IntegerField(default=15)
    connected_intersections = models.JSONField(default=list, blank=True)
    
    baseline_metrics = models.JSONField(default=dict)
    simulated_metrics = models.JSONField(default=dict)
    delta_metrics = models.JSONField(default=dict)
    network_impact = models.JSONField(default=dict)
    data_sources = models.JSONField(default=dict)
    ai_explanation = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Simulation Result"
        verbose_name_plural = "Simulation Results"

    def __str__(self):
        return f"Sim: {self.intersection_id} ({self.current_green_seconds}s -> {self.proposed_green_seconds}s)"


class ModelVersion(models.Model):
    """
    Safe Model Retraining & Version Tracking (Feature 6).
    """
    version_id = models.CharField(max_length=100, unique=True)
    model_type = models.CharField(max_length=50)  # impact_regressor, anomaly_detector, ripple_predictor
    file_path = models.CharField(max_length=255)
    training_timestamp = models.DateTimeField(auto_now_add=True)
    dataset_size = models.IntegerField(default=0)
    features = models.JSONField(default=list)
    metrics = models.JSONField(default=dict)
    validation_score = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)
    promoted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-training_timestamp"]
        verbose_name = "Model Version"
        verbose_name_plural = "Model Versions"

    def __str__(self):
        status = "ACTIVE" if self.is_active else "STAGED"
        return f"Model {self.version_id} ({self.model_type}) [{status}]"


class TrafficAnomaly(models.Model):
    """
    Traffic Anomaly Detection (Feature 7).
    """
    SEVERITY_CHOICES = [
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
        ("CRITICAL", "Critical"),
    ]

    intersection = models.ForeignKey(
        Intersection, on_delete=models.CASCADE, related_name="traffic_anomalies"
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    anomaly_score = models.FloatField(default=0.0)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="MEDIUM")
    anomaly_type = models.CharField(max_length=50, default="UNUSUAL_SURGE")
    confidence = models.FloatField(default=85.0)
    supporting_metrics = models.JSONField(default=dict)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-detected_at"]
        verbose_name = "Traffic Anomaly"
        verbose_name_plural = "Traffic Anomalies"

    def __str__(self):
        return f"Anomaly [{self.severity}]: {self.intersection_id} - {self.anomaly_type}"

