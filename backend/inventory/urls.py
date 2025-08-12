from django.urls import path
from . import views

urlpatterns = [
    path('health', views.health),  # kleiner Ping, zum Test
]
