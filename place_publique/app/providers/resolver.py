import os
from typing import Dict
from .base import ResolveResult
from . import earthcam, skyline


def _env_key(camera_id: str, suffix: str) -> str:
    return f"CAM_{camera_id.upper()}_{suffix}"


def resolve_camera(camera: Dict) -> ResolveResult:
    camera_id = camera["id"]
    stream_override = os.getenv(_env_key(camera_id, "STREAM_URL"))
    snap_override = os.getenv(_env_key(camera_id, "SNAPSHOT_URL"))
    if stream_override or snap_override:
        return ResolveResult(
            stream_url=stream_override,
            snapshot_url=snap_override,
            status="ok",
            message="using override",
        )

    page_url = camera.get("page_url", "")
    if "earthcam" in page_url:
        return earthcam.resolve(page_url)
    if "skylinewebcams" in page_url:
        return skyline.resolve(page_url)

    return ResolveResult(status="needs_override", message="unknown provider")
