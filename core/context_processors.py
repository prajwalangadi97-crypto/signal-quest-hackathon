"""Context processor to inject nav items and system status into all templates."""

from prediction.registry import registry


def nav_context(request):
    nav_items = [
        {"url": "/dashboard/", "label": "Dashboard", "icon": "&#9638;", "id": "dashboard"},
        {"url": "/map/", "label": "Live Map", "icon": "&#9673;", "id": "map"},
        {"url": "/routing/", "label": "Route Planner", "icon": "&#10132;", "id": "routing"},
        {"url": "/map/intersections/", "label": "Intersections", "icon": "&#8942;", "id": "intersections"},
        {"url": "/signals/", "label": "Signals", "icon": "&#9899;", "id": "signals"},
        {"url": "/signals/decision-center/", "label": "Decision Center", "icon": "⚡", "id": "decision_center"},
        {"url": "/emergency/", "label": "Emergency", "icon": "&#9888;", "id": "emergency"},
        {"url": "/analytics/", "label": "Analytics", "icon": "&#9776;", "id": "analytics"},
        {"url": "/vision/", "label": "Vision", "icon": "&#128247;", "id": "vision"},
    ]

    user_role = getattr(request.user, "role", "admin")
    if user_role == "admin" or getattr(request.user, "is_superuser", True):
        nav_items.append(
            {"url": "/admin/", "label": "Admin", "icon": "&#9881;", "id": "admin"}
        )

    return {
        "nav_items": nav_items,
        "registry_healthy": registry.is_healthy() if registry._loaded else False,
    }
