import io
import uuid
from curl_cffi import requests
from minio import Minio
import logging

logger = logging.getLogger(__name__)


class MinIOClient:
    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, secure: bool = False
    ):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.secure = secure
        self.client = None
        self.get_client()

    def get_client(self):
        if self.client is not None:
            return self.client
        self.client = Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )

    def make_bucket(self, bucket_name: str, location="us-eaast-1") -> None:
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name, location)
            logger.info(f"Bucket {bucket_name} is created with region {location}")
        else:
            logger.warning(f"Bucket {bucket_name} already exists")

    def upload_text_to_minio(self, bucket_name, text_content, object_name) -> None:
        text_bytes = text_content.encode("utf-8")
        data_stream = io.BytesIO(text_bytes)

        result = self.client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=data_stream,
            length=len(text_bytes),
            content_type="text/plain",
        )

        logger.info(f"Upload {result.object_name} done")

    def upload_image_to_minio(self, bucket_name, image_url, object_name):
        try:
            response = requests.get(image_url, impersonate="chrome", timeout=30)

            response.raise_for_status()

            image_bytes = response.content

            if not image_bytes:
                raise Exception("empty image content")

            data_stream = io.BytesIO(image_bytes)

            content_type = response.headers.get(
                "content-type", "application/octet-stream"
            )

            result = self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data_stream,
                length=len(image_bytes),
                content_type=content_type,
            )

            logger.info(f"Upload {result.object_name} done")

        except Exception as e:
            logger.error(f"Error processing image " f"{image_url}: {e}", exc_info=True)
            raise
