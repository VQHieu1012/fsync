# worker.py
import os
import uuid
import signal
import time
import random
import logging
import hashlib
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from ..utils.minio_client import MinIOClient
from ..utils.elastic_client import ElasticSearchClient
from ..utils.logger import load_logger
from ..utils.helpers import get_extension

load_dotenv()
load_logger("logs/worker.log")

logger = logging.getLogger(__name__)

DB_URL = os.environ.get("DB_URL", "localhost:9000")
ENDPOINT = os.environ.get("ENDPOINT")
ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
secure_env = os.environ.get("MINIO_SECURE", "False").strip().lower()
SECURE = secure_env in ("true", "1", "yes")
RAW_BUCKET = os.environ.get("SECRET_RAW_BUCKETKEY", "cafef-xahoi")

ELASTIC_HOST = os.environ.get("ELASTIC_HOST", "http://192.168.0.115:9200")
INDEX = os.environ.get("INDEX", "default")

MAX_RETRIES = 5
PROCESSING_TIMEOUT_SECONDS = 30

engine = create_engine(DB_URL)

s3 = MinIOClient(
    endpoint=ENDPOINT,  # type: ignore
    access_key=ACCESS_KEY,  # type: ignore
    secret_key=SECRET_KEY,  # type: ignore
    secure=SECURE,  # type: ignore
)

es = ElasticSearchClient(ELASTIC_HOST)

is_shutting_down = False


def handle_shutdown_signal(signum, frame):
    global is_shutting_down
    logger.info("(Control - C) Handling...")
    is_shutting_down = True


def claim_article():

    query = text(f"""
        WITH cte AS (
            SELECT
                article_id,
                CASE
                    WHEN status = 'processing'
                    THEN TRUE
                    ELSE FALSE
                END AS reclaimed
            FROM articles
            WHERE
                (
                    status = 'pending'
                    AND (
                        next_retry_at IS NULL
                        OR next_retry_at <= NOW()
                    )
                )
                OR
                (
                    status = 'processing'
                    AND processing_started_at < NOW() - INTERVAL '{PROCESSING_TIMEOUT_SECONDS} seconds'
                )

            ORDER BY discovered_at
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        UPDATE articles a
        SET
            status = 'processing',
            processing_started_at = NOW()
        FROM cte
        WHERE a.article_id = cte.article_id
        RETURNING
            a.article_id,
            a.article_url,
            a.source_name,
            cte.reclaimed
        """)

    with engine.begin() as conn:

        result = conn.execute(query)

        row = result.mappings().first()

        if not row:
            return None

        article = dict(row)

        if article["reclaimed"]:

            logger.warning(f"reclaimed stuck job: " f"{article['article_id']}")

        return article


def mark_done(article_id: int, raw_s3_key: str):

    query = text("""
        UPDATE articles
        SET
            status = 'done',
            raw_s3_key = :raw_s3_key,
            processed_at = NOW()
        WHERE article_id = :article_id
        """)

    with engine.begin() as conn:

        conn.execute(
            query,
            {
                "article_id": article_id,
                "raw_s3_key": raw_s3_key,
            },
        )


def mark_failed(article_id: int, error_message: str):

    query = text("""
        UPDATE articles
        SET
            retry_count = retry_count + 1,
            last_error = :error_message,
            status = CASE
                WHEN retry_count + 1 >= :max_retries
                THEN 'failed'
                ELSE 'pending'
            END,
            failed_at = CASE
                WHEN retry_count + 1 >= :max_retries
                THEN NOW()
                ELSE failed_at
            END,
            next_retry_at = CASE
                WHEN retry_count + 1 >= :max_retries
                THEN NULL

                ELSE NOW() +
                    (
                        INTERVAL '1 second'
                        *
                        LEAST(
                            POWER(2, retry_count) * 60,
                            3600
                        )
                    )
            END
        WHERE article_id = :article_id
        """)

    with engine.begin() as conn:
        conn.execute(
            query,
            {
                "article_id": article_id,
                "error_message": error_message[:5000],
                "max_retries": MAX_RETRIES,
            },
        )


def fetch_html(url: str) -> str:
    response = requests.get(url, impersonate="chrome", timeout=30)

    response.raise_for_status()

    return response.text


def extract_images(html: str):

    soup = BeautifulSoup(html, "html.parser")

    images = []

    for img in soup.select("img[type='photo']"):
        src = img.get("src")

        if not src:
            continue

        images.append(src)

    return images


def extract_content(html: str):

    soup = BeautifulSoup(html, "html.parser")

    try:
        title = soup.select_one("h1.title").get_text(separator=" ", strip=True)

        detail_sapo = soup.select_one("h2.sapo").get_text(separator=" ", strip=True)

        author = soup.select_one("span.author").get_text(separator=" ", strip=True)
        author = author.replace("Theo ", "").strip()

        raw_date_str = soup.select_one("span[data-role='publishdate']").get_text(
            strip=True
        )
        clean_str = raw_date_str.split("AM")[0].split("PM")[0].strip()
        date_obj = datetime.strptime(clean_str, "%d-%m-%Y - %H:%M")
        formatted_date = date_obj.strftime("%Y-%m-%d-%H-%M")

        content = soup.select_one("div.detail-content.afcbc-body").get_text(
            separator="\n", strip=True
        )

        result = {
            "title": title,
            "detail_sapo": detail_sapo,
            "author": author,
            "published_at": formatted_date,
            "content": content,
        }
        # logger.info(f"PRERESULT: {result}")
        return result
    except Exception as e:
        logger.error(f"Eror extracting data with error {e}", exc_info=True)
        raise


def process_article(article):

    article_id = article["article_id"]
    article_url = article["article_url"]
    source_name = article["source_name"]
    raw_s3_key = f"{RAW_BUCKET}/{article_id}/"

    logger.info(f"processing: {article_url}")
    try:
        html = fetch_html(article_url)

        images = extract_images(html)
        result = extract_content(html)
        result.update({"post_id": article_id, "post_url": article_url})
        # logger.info(f"RESULT: {result}")

        for image_url in images:
            try:
                id = hashlib.sha256(image_url.encode()).hexdigest()
                ext = get_extension(image_url)
                s3.upload_image_to_minio(
                    RAW_BUCKET, image_url, f"{article_id}/{id}{ext}"
                )
            except Exception as e:
                logger.info(f"image upload failed: {image_url}, {e}")

        es.insert(index_name=INDEX, document=result, doc_id=result["post_id"])

        mark_done(article_id, raw_s3_key)
        logger.info(f"done: {article_id}")
    except Exception as e:
        logger.error(f"Process failed: {article_url}", exc_info=True)

        mark_failed(article_id, str(e))


def worker_loop():
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    if not es.index_exists(INDEX):
        mapping = {
            "post_id": {"type": "keyword"},
            "post_url": {"type": "keyword", "index": False},
            "title": {
                "type": "text",
                "analyzer": "vietnamese_analyzer",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "detail_sapo": {"type": "text", "analyzer": "vietnamese_analyzer"},
            "content": {"type": "text", "analyzer": "vietnamese_analyzer"},
            "author": {"type": "keyword"},
            "published_at": {
                "type": "date",
                "format": "yyyy-MM-dd HH:mm||yyyy-MM-dd-HH-mm||strict_date_optional_time||epoch_millis",
            },
        }
        es.create_index(INDEX, mapping)

    while not is_shutting_down:

        article = claim_article()

        if not article:
            logger.info("no pending jobs")
            for _ in range(5):
                if is_shutting_down:
                    break
                time.sleep(1)
            continue

        try:
            process_article(article)

        except Exception as e:
            logger.error(f"Worker failed: {e}")
            mark_failed(article["article_id"], str(e))
    logger.info("All done. Shutdown successfully")


if __name__ == "__main__":

    worker_loop()
