from django.urls import path

from . import views
from . import api_views

app_name = "signals_app"

urlpatterns = [
    path("", views.signals_list, name="signals_list"),
    path("<int:pk>/override/", views.signal_override, name="signal_override"),
    path("decision-center/", views.decision_center_view, name="decision_center"),
    # New IntelliFlow 2.0 REST APIs
    path("api/simulate-impact/", api_views.simulate_impact_api, name="api_simulate_impact"),
    path("api/optimize-network/", api_views.optimize_network_api, name="api_optimize_network"),
    path("api/impact-history/", api_views.impact_history_api, name="api_impact_history"),
    path("api/learning-performance/", api_views.learning_performance_api, name="api_learning_performance"),
    path("api/anomalies/", api_views.anomalies_api, name="api_anomalies"),
    path("api/feedback/", api_views.apply_feedback_api, name="api_feedback"),
    path("api/retrain/", api_views.safe_retrain_api, name="api_retrain"),
]

