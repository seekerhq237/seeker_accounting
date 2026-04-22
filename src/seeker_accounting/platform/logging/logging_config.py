from __future__ import annotations

import logging
import logging.config

from seeker_accounting.config.constants import LOG_FILENAME
from seeker_accounting.config.settings import AppSettings


def configure_logging(settings: AppSettings) -> logging.Logger:
    log_file = settings.runtime_paths.logs / LOG_FILENAME
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": settings.log_level,
                    "formatter": "standard",
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": settings.log_level,
                    "formatter": "standard",
                    "filename": str(log_file),
                    "maxBytes": 1_048_576,
                    "backupCount": 3,
                    "encoding": "utf-8",
                },
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["console", "file"],
            },
        }
    )
    logger = logging.getLogger("seeker_accounting")
    logger.debug("Logging configured.")
    return logger

