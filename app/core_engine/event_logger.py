import logging
try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    structlog = None
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("security_gateway")

from typing import Dict, Any
from app.db.database import log_event

class SecurityEventLogger:
    """
    Structured Logging & Persistent Audit Logger.
    Outputs machine-parseable JSON logs and records events in database.
    """
    def log(self, event_data: Dict[str, Any]):
        if structlog is not None:
            logger.info("security_event", **event_data)
        else:
            logger.info(f"security_event: {event_data}")
            
        try:
            log_event(event_data)
        except Exception as e:
            if hasattr(logger, "error"):
                logger.error(f"db_logging_failed: {e}")

event_logger = SecurityEventLogger()
