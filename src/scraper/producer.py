# uv run python -m src.scraper.producer

import os
import re
import time
import random
import asyncio
import logging
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from ..utils.logger import load_logger
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
load_logger()

logger = logging.getLogger(__name__)


DB_URL = os.environ.get("DB_URL", "localhost:9000")

SOURCE_NAME = "cafef_xahoi"

BASE_URL = "https://m.cafef.vn"

ARTICLE_REGEX = re.compile(r"-(\d+)\.chn$")

STOP_OLD_THRESHOLD = 20

CONCURRENT_PAGES = 10

MAX_PAGES = 3060

engine = create_engine(DB_URL)


async def fetch_html(session: AsyncSession, url: str) -> str:
    response = await session.get(url, impersonate="chrome", timeout=20)

    response.raise_for_status()

    return response.text


async def fetch_page(
    session: AsyncSession,
    sem: asyncio.Semaphore,
    page_url: str,
):
    async with sem:
        try:
            html = await fetch_html(session, page_url)

            await asyncio.sleep(random.uniform(0.5, 1.5))

            return {
                "url": page_url,
                "html": html,
                "error": None,
            }

        except Exception as e:
            return {
                "url": page_url,
                "html": None,
                "error": str(e),
            }


def construct_url(html: str):
    soup = BeautifulSoup(html, "html.parser")
    timeline_list = soup.select_one("div.configHidden > input[id='hdZoneId']").get("value")  # type: ignore
    logger.info(f"timeline_list::{timeline_list}")
    return f"{BASE_URL}/timelinelist/{timeline_list}"


def get_checkpoint() -> int:

    query = text("""
        SELECT COALESCE(MAX(article_id), 0)
        FROM articles
        WHERE source_name = :source_name
        """)

    with engine.begin() as conn:
        result = conn.execute(
            query,
            {
                "source_name": SOURCE_NAME,
            },
        ).scalar()

        return int(result)  # type: ignore


def extract_articles(html: str):
    soup = BeautifulSoup(html, "html.parser")

    results = []
    visited = set()

    for a_tag in soup.select("h3 > a"):
        href = a_tag.get("href")

        if not href:
            continue

        article_url = urljoin(BASE_URL, href)  # type: ignore

        if article_url in visited:
            continue

        visited.add(article_url)

        match = ARTICLE_REGEX.search(article_url)

        if not match:
            continue

        article_id = int(match.group(1))

        results.append(
            {
                "article_id": article_id,
                "article_url": article_url,
            }
        )

    return results


def insert_articles(items: list[dict]):
    query = text("""
        INSERT INTO articles (
            article_id,
            source_name,
            article_url
        )
        VALUES (
            :article_id,
            :source_name,
            :article_url
        )
        ON CONFLICT (article_id)
        DO NOTHING
        """)

    data = [
        {
            "article_id": item["article_id"],
            "source_name": SOURCE_NAME,
            "article_url": item["article_url"],
        }
        for item in items
    ]

    with engine.begin() as conn:
        if data:
            conn.execute(query, data)


async def crawl():

    checkpoint = get_checkpoint()

    logger.info(f"Checkpoint: {checkpoint}")

    async with AsyncSession() as session:
        html = await fetch_html(session, "https://m.cafef.vn/xa-hoi.chn")
        base_url = construct_url(html)

        sem = asyncio.Semaphore(CONCURRENT_PAGES)

        page = 1

        old_count = 0

        empty_pages = 0

        while page <= MAX_PAGES:
            batch_pages = list(range(page, page + CONCURRENT_PAGES))
            tasks = []

            for p in batch_pages:
                page_url = f"{base_url}/{page}.chn"
                tasks.append(fetch_page(session, sem, page_url))

            results = await asyncio.gather(*tasks)

            stop = False

            for result in results:
                page_url = result["url"]

                if result["error"]:
                    logger.info(
                        f"fetch failed: " f"{page_url} -> " f"{result['error']}"
                    )
                    continue

                html = result["html"]

                articles = extract_articles(html)

                logger.info(f"{page_url} -> " f"{len(articles)} articles")

                if not articles:

                    empty_pages += 1

                    logger.info(f"empty_pages=" f"{empty_pages}")

                    if empty_pages >= 3:
                        logger.info("too many empty pages")
                        stop = True
                        break

                    continue

                empty_pages = 0

                new_articles = []

                for article in articles:

                    article_id = article["article_id"]

                    if article_id > checkpoint:
                        new_articles.append(article)
                        old_count = 0

                    else:
                        old_count += 1

                if new_articles:

                    insert_articles(new_articles)

                    logger.info(f"inserted=" f"{len(new_articles)}")

                logger.info(f"old_count=" f"{old_count}")

                if old_count >= STOP_OLD_THRESHOLD:
                    logger.info("stop threshold reached")
                    stop = True
                    break

            if stop:
                break

            page += CONCURRENT_PAGES


if __name__ == "__main__":

    asyncio.run(crawl())
