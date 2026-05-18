import logging
import time
from pathlib import Path
import os
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv


def generate_safe_filepath(file_path_str: str) -> str:
    path = Path(file_path_str)
    if path.exists():
        timestamp_int = int(time.time())
        new_filename = f"{path.stem}_{timestamp_int}{path.suffix}"
        path = path.with_name(new_filename)

    return str(path)


class AppLogger:
    @staticmethod
    def setup(log_filepath=None):
        load_dotenv()

        if log_filepath is None:
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            log_filepath = os.path.join(log_dir, "crawler.log")
        else:
            parent_dir = os.path.dirname(log_filepath)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir)

        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        numeric_level = getattr(logging, log_level_str, logging.INFO)

        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        file_handler = RotatingFileHandler(
            log_filepath, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        console_handler = logging.StreamHandler()

        logging.basicConfig(
            level=numeric_level,
            format=log_format,
            handlers=[file_handler, console_handler],
            force=True,
        )

        logger = logging.getLogger("AppLogger")
        logger.info(f"Logger initialized. Logging to: {log_filepath}")

        return logger


def load_logger(log_filepath=None):
    if log_filepath is not None:
        # Tự động đổi tên nếu file người dùng truyền vào bị trùng
        log_filepath = generate_safe_filepath(log_filepath)

    return AppLogger.setup(log_filepath)
