import logging
from logging.handlers import RotatingFileHandler
import os

# Define the log directory and file
LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "sync_service.log")

# Setup logging configuration
logger = logging.getLogger("sync_service")
logger.setLevel(logging.INFO)

# Clear existing handlers to prevent duplicate logs in case of reload
if logger.hasHandlers():
    logger.handlers.clear()

# Formatter: [Timestamp] [Level] [LoggerName]: Message
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Rotating File Handler (5MB size, max 5 backups)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def sanitize_text(value):
    if value is None:
        return ""

    value = str(value)

    # remove emojis / unsupported 4-byte characters
    value = value.encode("utf-8", "ignore").decode("utf-8", "ignore")

    # keep text clean
    return value.strip()