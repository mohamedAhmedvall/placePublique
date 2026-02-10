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
        return ResolveResult(status="error", message=f"earthcam fetch failed: {exc}")

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ") + " " + html

    m3u8 = re.findall(r"https?://[^\"'\s]+\.m3u8[^\"'\s]*", text)
    images = re.findall(r"https?://[^\"'\s]+\.(?:jpg|jpeg|png)[^\"'\s]*", text, flags=re.IGNORECASE)

    return ResolveResult(
        stream_url=m3u8[0] if m3u8 else None,
        snapshot_url=images[0] if images else None,
        status="ok" if (m3u8 or images) else "needs_override",
        message="No direct media found" if not (m3u8 or images) else "",
    )
