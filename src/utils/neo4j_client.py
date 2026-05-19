import logging
from neo4j import GraphDatabase, exceptions

logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(
        self, uri: str = "bolt://localhost:7687", auth: tuple = ("neo4j", "password")
    ):
        self.uri = uri
        self.auth = auth
        self.driver = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        if not self.driver:
            try:
                self.driver = GraphDatabase.driver(self.uri, auth=self.auth)

                self.driver.verify_connectivity()
                logger.info("Neo4j connected")
            except exceptions.DriverError as e:
                logger.error(f"Connect to Neo4j failed: {e}")
                raise

    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None
            logger.info("Neo4j connection closed")

    def query(self, cypher_query: str, parameters: dict = None, db: str = None):
        if not self.driver:
            raise RuntimeError("Driver is not open. Use open() or 'with'.")

        parameters = parameters or {}

        try:
            result, summary, keys = self.driver.execute_query(
                cypher_query, parameters_=parameters, database_=db
            )

            return result, summary, keys
        except exceptions.CypherSyntaxError as e:
            logger.error(f"Error Cypher: {e}")
            raise

    def clear_database(self, db: str = None):
        query = "MATCH (n) DETACH DELETE n"
        self.query(query, db=db)
        logger.info("Database is cleared.")
