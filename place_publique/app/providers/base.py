from dataclasses import dataclass
from typing import Optional


@dataclass
class ResolveResult:
    stream_url: Optional[str] = None
    snapshot_url: Optional[str] = None
    status: str = "ok"
    message: str = ""
