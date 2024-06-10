from neo4j import GraphDatabase
from django.conf import settings
import os
from loguru import logger


class Neo4jService:
    def __init__(self):
        if os.getenv("USE_LOCAL_NEO4J", "False") != "False":
            # use local
            URI = os.getenv("NEO4J_LOCAL_URI")
            AUTH = (
                os.getenv("NEO4J_LOCAL_USERNAME"),
                os.getenv("NEO4J_LOCAL_PASSWORD"),
            )

            self._neo4j_driver = GraphDatabase.driver(
                URI,
                auth=AUTH,
                # encrypted=True,
                # trust=TRUST_SYSTEM_CA_SIGNED_CERTIFICATES,
            )

            self._neo4j_driver.verify_connectivity()
            logger.info("Verified connectivity to local Neo4j")
        else:
            URI = os.getenv("NEO4J_URI")
            AUTH = (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))

            self._neo4j_driver = GraphDatabase.driver(
                URI,
                auth=AUTH,
                # encrypted=True,
                # trust=TRUST_SYSTEM_CA_SIGNED_CERTIFICATES,
            )

            self._neo4j_driver.verify_connectivity()
            logger.info("Verified connectivity to cloud Neo4j")

    def close(self):
        self._neo4j_driver.close()

    def run_query(self, query):
        with self._neo4j_driver.session() as session:
            result = session.run(query)
            return [record.data() for record in result]


# Initialize the service instance
neo4j_service = Neo4jService()
