from neo4j import GraphDatabase
from django.conf import settings


class Neo4jService:
    def __init__(self):
        print("NEO4J_URI: ", settings.NEO4J_URI)
        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
        )

    def close(self):
        self._driver.close()

    def run_query(self, query):
        with self._driver.session() as session:
            result = session.run(query)
            return [record.data() for record in result]


# Initialize the service instance
neo4j_service = Neo4jService()
