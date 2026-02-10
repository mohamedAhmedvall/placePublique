import re
import requests
from bs4 import BeautifulSoup
from .base import ResolveResult


def resolve(page_url: str, timeout: int = 10) -> ResolveResult:
    try:
        resp = requests.get(page_url, timeout=timeout)
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        return ResolveResult(status="error", message=f"skyline fetch failed: {exc}")

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ") + " " + html

    m3u8 = re.findall(r"https?://[^\"'\s]+\.m3u8[^\"'\s]*", text)
    mp4 = re.findall(r"https?://[^\"'\s]+\.mp4[^\"'\s]*", text)
    images = re.findall(r"https?://[^\"'\s]+\.(?:jpg|jpeg|png)[^\"'\s]*", text, flags=re.IGNORECASE)

    stream = m3u8[0] if m3u8 else (mp4[0] if mp4 else None)
    return ResolveResult(
        stream_url=stream,
        snapshot_url=images[0] if images else None,
        status="ok" if (stream or images) else "needs_override",
        message="No direct media found" if not (stream or images) else "",
    )
