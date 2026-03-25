from django.contrib import admin
from django.urls import path

from trading.views import (
    dashboard_view,
    start_bot,
    stop_bot,
    reset_bot
)

urlpatterns = [

    path("", dashboard_view),

    path("start/", start_bot),

    path("stop/", stop_bot),

    path("reset/", reset_bot),  # ⭐ เพิ่ม
]