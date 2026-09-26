from django.shortcuts import redirect


def login_view(request):
    """Directly redirects to dashboard without rendering any login page."""
    next_url = request.GET.get("next")
    if next_url and next_url != "/accounts/login/":
        return redirect(next_url)
    return redirect("dashboard:home")


def logout_view(request):
    """Directly redirects to dashboard without logging out or showing login page."""
    return redirect("dashboard:home")

