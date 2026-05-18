import logging
from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)


class ElasticSearchClient:
    def __init__(
        self,
        host: str = "http://localhost:9200",
        username: str = None,
        password: str = None,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.client = None

        self._connect()

    def _connect(self):
        try:
            if self.username and self.password:
                self.client = Elasticsearch(
                    self.host,
                    basic_auth=(self.username, self.password),
                    verify_certs=False,
                )
            else:
                self.client = Elasticsearch(self.host)

            if self.client.ping():
                logging.info(f"Connect to Elasticsearch successfully: {self.host}")
            else:
                logging.error(f"Ping failed Elasticsearch: {self.host}")
                self.client = None
        except Exception as e:
            logging.error(f"Critical error when connect to Elasticsearch: {e}")
            self.client = None

    def get_info(self):
        if not self.client:
            return {"error": "Cannect ES failed"}
        return self.client.info()

    def index_exists(self, index_name: str) -> bool:
        if not self.client:
            return False
        return self.client.indices.exists(index=index_name).body

    def create_index(
        self,
        index_name: str,
        mapping_properties: dict = None,
        analyzer_config: dict = None,
    ):
        if not self.client:
            logging.error("Elasticsearch is not connected")
            return None

        if self.index_exists(index_name):
            logging.info(
                f"ℹ Index '{index_name}' already exists. Skipping create index {index_name}"
            )
            return False

        body = {
            "settings": {
                "analysis": {
                    "analyzer": {
                        "vietnamese_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "asciifolding"],
                        }
                    }
                }
            }
        }

        if analyzer_config:
            body["settings"]["analysis"]["analyzer"].update(analyzer_config)

        if mapping_properties:
            body["mappings"] = {"properties": mapping_properties}

        try:
            response = self.client.indices.create(index=index_name, body=body)
            logging.info(f"Index created: '{index_name}'")
            return response
        except Exception as e:
            logging.error(f"Error when creating Index '{index_name}': {e}")
            return None

    def insert(self, index_name: str, document: dict, doc_id: str = None):
        try:
            response = self.client.index(index=index_name, id=doc_id, document=document)
            logging.info(
                f"Insert document successfully. ID: {response['_id']}. Result: {response['result']}"
            )
            return response
        except Exception as e:
            logging.error(f"Error when inserting document: {e}")
            return None

    def bulk_insert(self, index_name: str, data_list: list, id_key: str = None):
        try:
            actions = []
            for item in data_list:
                action = {"_index": index_name, "_source": item}
                if id_key and id_key in item:
                    action["_id"] = item[id_key]
                actions.append(action)

            success, errors = helpers.bulk(self.client, actions)
            logging.info(f"Bulk {success} records to index '{index_name}'")
            return success, errors
        except Exception as e:
            logging.error(f"Error when executing bulk insert: {e}")
            return 0, str(e)

    def get_by_id(self, index_name: str, doc_id: str):
        try:
            response = self.client.get(index=index_name, id=doc_id)
            return response["_source"]
        except Exception as e:
            logging.warning(
                f"No document ID {doc_id} in index {index_name}. With error: {e}"
            )
            return None

    def update(self, index_name: str, doc_id: str, update_data: dict):
        try:
            response = self.client.update(index=index_name, id=doc_id, doc=update_data)
            logging.info(f"Update ID {doc_id}. Result: {response['result']}")
            return response
        except Exception as e:
            logging.error(f"Error when updating document ID {doc_id}: {e}")
            return None

    def delete(self, index_name: str, doc_id: str):
        try:
            response = self.client.delete(index=index_name, id=doc_id)
            logging.info(f"Delete ID {doc_id}. Result: {response['result']}")
            return response
        except Exception as e:
            logging.error(f"Error when deleting ID {doc_id}: {e}")
            return None

    def search(self, index_name: str, query_dsl: dict):
        try:
            response = self.client.search(index=index_name, query=query_dsl)
            results = [
                {"id": hit["_id"], "score": hit["_score"], "source": hit["_source"]}
                for hit in response["hits"]["hits"]
            ]
            return results
        except Exception as e:
            logging.error(f"Error when searching: {e}")
            return []
