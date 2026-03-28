from django.contrib import admin
from django.urls import path

from trading.views import (
    dashboard_view,
    start_bot,
    stop_bot,
    reset_bot,
    set_real_mode,
    set_test_mode
)

urlpatterns = [

    path("", dashboard_view),

    path("start/", start_bot),

    path("stop/", stop_bot),

    path("reset/", reset_bot), 

    path("set_real/",set_real_mode),

    path("set_test/",set_test_mode),
]