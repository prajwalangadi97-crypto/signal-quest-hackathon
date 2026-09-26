"""Auto-login middleware to allow direct, unauthenticated access to the full interface."""

import logging
from django.contrib.auth import get_user_model

logger = logging.getLogger("core")


class AutoLoginMiddleware:
    """Assigns the primary admin user to any unauthenticated request, bypassing all login requirements."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            User = get_user_model()
            admin_user = (
                User.objects.filter(role="admin").first()
                or User.objects.filter(is_superuser=True).first()
                or User.objects.filter(is_active=True).first()
            )
            if not admin_user:
                try:
                    admin_user = User.objects.create_superuser(
                        username="admin",
                        password="adminpassword",
                        role="admin",
                    )
                except Exception as e:
                    logger.warning("Could not auto-create admin user: %s", e)
                    admin_user = None

            if admin_user:
                request.user = admin_user

        return self.get_response(request)
