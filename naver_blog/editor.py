"""SE Editor component helpers — HTML-to-component conversion via Naver upconvert API."""

import requests

from naver_blog.session import USER_AGENT

UPCONVERT_URL = "https://upconvert.editor.naver.com/blog/html/components"


class EditorError(Exception):
    """Raised on editor/upconvert errors."""


def html_to_components(html: str, blog_id: str, session: requests.Session) -> list[dict]:
    """Convert HTML to Naver SE editor components via the upconvert API.

    Wraps the HTML in the expected fragment format before sending.
    """
    wrapped = (
        f"<html>\n<body>\n<!--StartFragment-->\n{html}\n<!--EndFragment-->\n</body>\n</html>"
    )
    url = f"{UPCONVERT_URL}?documentWidth=886&userId={blog_id}"
    resp = session.post(
        url,
        data=wrapped.encode("utf-8"),
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "User-Agent": USER_AGENT,
            "Referer": f"https://blog.naver.com/PostWriteForm.naver?blogId={blog_id}",
        },
        timeout=30,
    )
    resp.raise_for_status()

    try:
        data = resp.json()
    except ValueError as exc:
        raise EditorError(f"upconvert returned non-JSON: {resp.text[:200]}") from exc

    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "components" in data:
        return data["components"]
    return [data]


def create_title_component(title: str) -> dict:
    """Create a documentTitle SE component."""
    return {
        "@ctype": "documentTitle",
        "title": [{"@ctype": "text", "text": title}],
        "layout": "default",
        "align": "left",
    }


def create_image_component(img_data: dict) -> dict:
    """Create an image SE component from upload response data.

    Args:
        img_data: dict with url, width, height, filename keys.
    """
    return {
        "@ctype": "image",
        "src": img_data["url"],
        "width": img_data.get("width", 0),
        "height": img_data.get("height", 0),
        "fileName": img_data.get("filename", ""),
        "caption": "",
        "layout": "default",
        "align": "center",
    }
