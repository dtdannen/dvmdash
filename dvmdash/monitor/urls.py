from django.urls import path
from django.urls import re_path
from . import views

# app_name = 'monitor'

urlpatterns = [
    path("", views.overview, name="overview"),
    path("dvm/", views.dvm, name="dvm"),
    path("dvm/<str:pub_key>/", views.dvm, name="dvm_with_pub_key"),
    path("kind/", views.kind, name="kind"),
    path("kind/<str:kind_num>/", views.kind, name="kind_with_kind_num"),
]
