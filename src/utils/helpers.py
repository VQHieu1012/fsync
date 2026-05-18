from urllib.parse import urlparse
from pathlib import Path


def get_extension(image_url: str):

    path = urlparse(image_url).path
    ext = Path(path).suffix

    if not ext:
        ext = ".jpg"
    return ext
