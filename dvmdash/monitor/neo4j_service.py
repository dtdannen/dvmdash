from neo4j import GraphDatabase
import os
from loguru import logger
from typing import Optional, ClassVar


class Neo4jService:
    """
    A singleton service class for Neo4j database operations.
    Ensures only one connection is maintained throughout the application.
    """

    _instance: ClassVar[Optional["Neo4jService"]] = None
    _driver: ClassVar[Optional[GraphDatabase.driver]] = None

    def __new__(cls):
        """Ensure singleton pattern is enforced at instantiation"""
        if cls._instance is None:
            cls._instance = super(Neo4jService, cls).__new__(cls)
            cls._initialize_driver()
        return cls._instance

    @classmethod
    def _initialize_driver(cls) -> None:
        """Initialize the Neo4j driver with appropriate configuration"""
        if cls._driver is not None:
            return

        try:
            if os.getenv("USE_LOCAL_NEO4J", "False") != "False":
                cls._setup_local_connection()
            else:
                cls._setup_cloud_connection()

            cls._driver.verify_connectivity()
            logger.info(
                f"Verified connectivity to {'local' if os.getenv('USE_LOCAL_NEO4J', 'False') != 'False' else 'cloud'} Neo4j"
            )

        except Exception as e:
            logger.error(f"Failed to initialize Neo4j connection: {str(e)}")
            raise

    @classmethod
    def _setup_local_connection(cls) -> None:
        """Set up connection to local Neo4j instance"""
        uri = os.getenv("NEO4J_LOCAL_URI")
        auth = (
            os.getenv("NEO4J_LOCAL_USERNAME"),
            os.getenv("NEO4J_LOCAL_PASSWORD"),
        )

        if not all([uri, auth[0], auth[1]]):
            raise ValueError("Missing required local Neo4j environment variables")

        cls._driver = GraphDatabase.driver(uri, auth=auth)

    @classmethod
    def _setup_cloud_connection(cls) -> None:
        """Set up connection to cloud Neo4j instance"""
        uri = os.getenv("NEO4J_URI")
        auth = (
            os.getenv("NEO4J_USERNAME"),
            os.getenv("NEO4J_PASSWORD"),
        )

        if not all([uri, auth[0], auth[1]]):
            raise ValueError("Missing required cloud Neo4j environment variables")

        logger.debug(f"NEO4J URI: {uri}")
        cls._driver = GraphDatabase.driver(uri, auth=auth)

    @classmethod
    def close(cls) -> None:
        """Close the Neo4j driver connection"""
        if cls._driver is not None:
            cls._driver.close()
            cls._driver = None
            logger.info("Neo4j connection closed")

    @classmethod
    def run_query(cls, query: str, params: Optional[dict] = None) -> list:
        """
        Execute a Neo4j query and return the results

        Args:
            query (str): The Cypher query to execute
            params (dict, optional): Query parameters

        Returns:
            list: List of query results
        """
        if cls._driver is None:
            raise RuntimeError("Neo4j driver not initialized")

        try:
            with cls._driver.session() as session:
                result = session.run(query, params or {})
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"Query execution failed: {str(e)}")
            raise

    def __del__(self) -> None:
        """Ensure driver is closed when the instance is destroyed"""
        self.close()
