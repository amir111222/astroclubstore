from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("callback/", views.callback, name="callback"),
    path("result/<str:order_number>/", views.result, name="result"),
]
