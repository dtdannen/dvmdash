from django.urls import path
from django.urls import re_path
from . import views

# app_name = 'monitor'

urlpatterns = [
    path("", views.overview, name="overview"),
]
