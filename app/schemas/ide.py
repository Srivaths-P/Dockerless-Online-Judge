from typing import Optional

from pydantic import BaseModel
from app.sandbox.engine import SandboxResult


class IdeRunRequest(BaseModel):
    code: str
    language: str
    input_str: Optional[str] = ""


class IdeRunResult(SandboxResult):
    pass
