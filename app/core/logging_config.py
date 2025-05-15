import logging
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
ACTIVITY_LOG_FILE = os.path.join(LOG_DIR, "user_activity.log")

activity_logger = logging.getLogger("user_activity")
activity_logger.setLevel(logging.INFO)

if not activity_logger.handlers:
    file_handler = logging.FileHandler(ACTIVITY_LOG_FILE)

    formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(formatter)
    activity_logger.addHandler(file_handler)

    activity_logger.propagate = False


def log_user_event(user_id: int, user_email: str, event_type: str, details: Optional[Dict[str, Any]] = None):
    try:
        event_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "user_email": user_email,
            "event_type": event_type,
            "details": details if details is not None else {}
        }

        activity_logger.info(json.dumps(event_data, ensure_ascii=False))
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to write user activity log event: {e}")