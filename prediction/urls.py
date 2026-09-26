from django.shortcuts import redirect
from django.urls import path

app_name = "prediction"

urlpatterns = [
    path("", lambda r: redirect("dashboard:home"), name="index"),
]
