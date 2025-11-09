import logging
import logging.handlers
import os
from datetime import datetime, timezone
from queue import Queue
from typing import Optional, Dict, Any

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False

startup_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
APP_LOG_FILENAME = f"app_{startup_timestamp}.log"

audit_handler = logging.handlers.RotatingFileHandler(
    os.path.join(LOG_DIR, "audit.log"), maxBytes=10 * 1024 * 1024, backupCount=5
)
audit_handler.setFormatter(logging.Formatter('%(message)s'))
audit_logger.addHandler(audit_handler)


def log_audit_event(username: str, ip_address: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    audit_logger.info(f"{timestamp} | USER: {username} | IP: {ip_address}")


def setup_app_logging_worker(log_queue: Queue):
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, APP_LOG_FILENAME), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app_handler.setFormatter(formatter)

    listener = logging.handlers.QueueListener(log_queue, app_handler, respect_handler_level=True)
    return listener


def setup_log_queue_handler():
    log_queue = Queue(-1)

    queue_handler = logging.handlers.QueueHandler(log_queue)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(queue_handler)

    listener = setup_app_logging_worker(log_queue)

    return log_queue, listener


def log_user_event(user_id: Optional[int], user_email: Optional[str], event_type: str,
                   details: Optional[Dict[str, Any]] = None):
    app_logger = logging.getLogger("app.user_events")
    event_data = {
        "user_id": user_id,
        "user_email": user_email,
        "event_type": event_type,
        "details": details or {}
    }
    app_logger.info(event_data)