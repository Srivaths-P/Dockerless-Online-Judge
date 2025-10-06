import os
from datetime import datetime, timedelta, timezone

import markdown
from fastapi.templating import Jinja2Templates

from app.ui.deps import get_flashed_messages

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEMPLATES_DIR = os.path.join(_PROJECT_ROOT, "templates")

if not os.path.exists(TEMPLATES_DIR):
    print(f"CRITICAL ERROR: Templates directory not found at {TEMPLATES_DIR}.")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["get_flashed_messages"] = get_flashed_messages
templates.env.globals["G"] = {"datetime_class": datetime, "timedelta_class": timedelta}
templates.env.add_extension('jinja2.ext.do')


def to_isoformat(dt: datetime) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


templates.env.filters["to_isoformat"] = to_isoformat


def markdown_filter(text):
    if text is None: return ""
    return markdown.markdown(
        text,
        extensions=[
            "fenced_code",
            "tables",
            "sane_lists",
            "extra",
            "codehilite",
            "pymdownx.arithmatex"

        ], extension_configs={
            "pymdownx.arithmatex": {
                "generic": True
            }
        }
    )


templates.env.filters["markdown"] = markdown_filter
