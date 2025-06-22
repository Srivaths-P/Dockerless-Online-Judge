import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

startup_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
ACTIVITY_LOG_FILE = os.path.join(LOG_DIR, f"activity_{startup_timestamp}.log")

activity_logger = logging.getLogger("user_activity")

if not activity_logger.handlers:
    activity_logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(ACTIVITY_LOG_FILE)

    formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(formatter)
    activity_logger.addHandler(file_handler)

    activity_logger.propagate = False

    activity_logger.info(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "application_startup",
        "details": {"log_file": ACTIVITY_LOG_FILE}
    }))


def log_user_event(user_id: Optional[int], user_email: Optional[str], event_type: str,
                   details: Optional[Dict[str, Any]] = None):
    event_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "user_email": user_email,
        "event_type": event_type,
        "details": details if details is not None else {}
    }

    try:
        activity_logger.info(json.dumps(event_data, ensure_ascii=False))
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to write user activity log event: {e}")
        print(f"Original event data: {event_data}")
