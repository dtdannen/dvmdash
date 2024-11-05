from django.apps import AppConfig
from .neo4j_service import Neo4jService


class MonitorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "monitor"

    def ready(self):
        Neo4jService()  # singleton service initialization
