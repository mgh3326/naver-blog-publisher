"""Naver Blog API client — ported from viruagent-cli naverApiClient.js."""

import json
import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from naver_blog.session import load_session, USER_AGENT

BLOG_HOST = "https://blog.naver.com"
EDITOR_HOST = "https://platform.editor.naver.com"
UPCONVERT_HOST = "https://upconvert.editor.naver.com"


class ApiError(Exception):
    """Raised on API errors."""


class SessionExpiredError(ApiError):
    """Raised when the session has expired."""


def _se_id() -> str:
    return f"SE-{uuid.uuid4()}"


class NaverBlogApi:
    """Naver Blog API client using saved session cookies."""

    def __init__(self, session: requests.Session, blog_id: str | None = None):
        self.session = session
        self.blog_id = blog_id

    @classmethod
    def from_session_file(cls, session_path: str = "~/.naver-blog/session.json", blog_id: str | None = None):
        session = load_session(session_path)
        return cls(session, blog_id)

    # ── Internal helpers ────────────────────────────────────────

    def _check_session_expired(self, text: str) -> None:
        """Detect session expiration from response text."""
        if "로그인" in text[:500] or "login" in text[:500].lower():
            raise SessionExpiredError("Session expired. Run 'naver-blog login' to re-authenticate.")

    def _get(self, url: str, **kwargs) -> requests.Response:
        resp = self.session.get(url, timeout=30, **kwargs)
        resp.raise_for_status()
        self._check_session_expired(resp.text)
        return resp

    def _post(self, url: str, **kwargs) -> requests.Response:
        resp = self.session.post(url, timeout=30, **kwargs)
        resp.raise_for_status()
        self._check_session_expired(resp.text)
        return resp

    def _referer(self, category_no: int | str = 0, extra: str = "") -> str:
        base = f"{BLOG_HOST}/PostWriteForm.naver?blogId={self.blog_id}&categoryNo={category_no}"
        return f"{base}&{extra}" if extra else base

    # ── Blog init ───────────────────────────────────────────────

    def init_blog(self) -> str:
        """Extract blogId from MyBlog.naver page."""
        resp = self._get(f"{BLOG_HOST}/MyBlog.naver", headers={"Referer": f"{BLOG_HOST}/"})
        match = re.search(r"blogId\s*=\s*'([^']+)'", resp.text)
        if not match:
            raise ApiError("Could not extract blogId from MyBlog.naver.")
        self.blog_id = match.group(1)
        return self.blog_id

    # ── Token & editor ──────────────────────────────────────────

    def get_token(self, category_no: int = 0) -> str:
        """Get Se-Authorization token."""
        if not self.blog_id:
            self.init_blog()
        resp = self._get(
            f"{BLOG_HOST}/PostWriteFormSeOptions.naver?blogId={self.blog_id}&categoryNo={category_no}",
            headers={"Referer": self._referer(category_no)},
        )
        data = resp.json()
        try:
            return data["result"]["token"]
        except (KeyError, TypeError) as exc:
            raise ApiError(f"Failed to get token: {data}") from exc

    def get_editor_info(self, category_no: int = 0) -> dict:
        """Get editorId + editorSource for posting.

        Returns:
            {"editor_id": str, "editor_source": str, "token": str}
        """
        if not self.blog_id:
            self.init_blog()

        token = self.get_token(category_no)

        # editorId from service_config
        resp = self._get(
            f"{EDITOR_HOST}/api/blogpc001/v1/service_config",
            headers={
                "Se-Authorization": token,
                "Referer": self._referer(category_no),
            },
        )
        config = resp.json()
        editor_id = config.get("editorInfo", {}).get("id", "")
        if not editor_id:
            raise ApiError(f"No editorId in service_config: {config}")

        # editorSource from manager options
        resp = self._get(
            f"{BLOG_HOST}/PostWriteFormManagerOptions.naver?blogId={self.blog_id}&categoryNo={category_no}",
            headers={"Referer": self._referer(category_no)},
        )
        mgr = resp.json()
        editor_source = mgr.get("result", {}).get("formView", {}).get("editorSource", "blogpc001")

        return {"editor_id": editor_id, "editor_source": editor_source, "token": token}

    # ── Categories ──────────────────────────────────────────────

    def get_categories(self) -> list[dict]:
        """Get blog category list."""
        if not self.blog_id:
            self.init_blog()
        resp = self._get(
            f"{BLOG_HOST}/PostWriteFormManagerOptions.naver?blogId={self.blog_id}",
            headers={"Referer": self._referer()},
        )
        data = resp.json()
        try:
            form_view = data["result"].get("formView", {})
            cat_view = form_view.get("categoryListFormView", {})
            categories = cat_view.get("categoryFormViewList", [])
            if not categories:
                categories = data["result"].get("categoryList", [])
        except (KeyError, TypeError):
            raise ApiError(f"Failed to get categories: {data}")

        return [
            {"id": c.get("categoryNo"), "name": c.get("categoryName", "")}
            for c in categories
        ]

    # ── HTML → SE Components ────────────────────────────────────

    def html_to_components(self, html: str) -> list[dict]:
        """Convert HTML to SE Editor components via upconvert API."""
        if not self.blog_id:
            self.init_blog()
        wrapped = f"<html>\n<body>\n<!--StartFragment-->\n{html}\n<!--EndFragment-->\n</body>\n</html>"
        resp = self._post(
            f"{UPCONVERT_HOST}/blog/html/components?documentWidth=886&userId={self.blog_id}",
            headers={"Content-Type": "text/html; charset=utf-8"},
            data=wrapped.encode("utf-8"),
        )
        components = resp.json()
        if not isinstance(components, list):
            raise ApiError(f"Unexpected upconvert response: {str(components)[:200]}")
        return components

    # ── Image upload ────────────────────────────────────────────

    def get_upload_session_key(self, token: str) -> str:
        """Get photo upload session key."""
        if not self.blog_id:
            self.init_blog()
        resp = self._get(
            f"{EDITOR_HOST}/api/blogpc001/v1/photo-uploader/session-key",
            headers={
                "Se-Authorization": token,
                "Referer": self._referer(),
            },
        )
        data = resp.json()
        key = data.get("sessionKey")
        if not key:
            raise ApiError(f"No sessionKey: {data}")
        return key

    def upload_image(self, image_path: str, token: str) -> dict:
        """Upload an image. Returns {url, width, height, filename, fileSize}."""
        if not self.blog_id:
            self.init_blog()

        session_key = self.get_upload_session_key(token)
        filepath = Path(image_path)
        filename = filepath.name

        # Detect MIME type
        ext = filepath.suffix.lower()
        mime = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp",
        }.get(ext, "image/png")

        upload_url = (
            f"https://blog.upphoto.naver.com/{session_key}/simpleUpload/0"
            f"?userId={self.blog_id}&extractExif=true&extractAnimatedCnt=true"
            f"&autorotate=true&extractDominantColor=false"
            f"&denyAnimatedImage=false&skipXcamFiltering=false"
        )

        with open(image_path, "rb") as f:
            resp = self._post(
                upload_url,
                files={"image": (filename, f, mime)},
                headers={"Referer": f"{BLOG_HOST}/{self.blog_id}"},
            )

        # Parse XML response
        def _tag(tag: str) -> str | None:
            m = re.search(f"<{tag}>([^<]*)</{tag}>", resp.text)
            return m.group(1) if m else None

        url = _tag("url")
        if not url:
            raise ApiError(f"Upload failed - no URL: {resp.text[:300]}")

        return {
            "url": url,
            "width": int(_tag("width") or 800),
            "height": int(_tag("height") or 600),
            "filename": _tag("fileName") or filename,
            "fileSize": int(_tag("fileSize") or 0),
        }

    @staticmethod
    def create_image_component(img_data: dict, represent: bool = False) -> dict:
        """Create SE Editor image component from upload result."""
        return {
            "id": _se_id(),
            "layout": "default",
            "align": "center",
            "src": f"https://blogfiles.pstatic.net/{img_data['url']}?type=w1",
            "internalResource": "true",
            "represent": "true" if represent else "false",
            "path": img_data["url"],
            "domain": "https://blogfiles.pstatic.net",
            "fileSize": img_data.get("fileSize", 0),
            "width": img_data["width"],
            "widthPercentage": 0,
            "height": img_data["height"],
            "originalWidth": img_data["width"],
            "originalHeight": img_data["height"],
            "fileName": img_data.get("filename", "image.jpg"),
            "caption": None,
            "format": "normal",
            "displayFormat": "normal",
            "imageLoaded": "true",
            "contentMode": "normal",
            "origin": {"srcFrom": "local", "@ctype": "imageOrigin"},
            "ai": "false",
            "@ctype": "image",
        }

    # ── Publish ─────────────────────────────────────────────────

    def publish_post(
        self,
        title: str,
        components: list[dict],
        category_no: int = 0,
        tags: str = "",
        open_type: int = 2,
    ) -> dict:
        """Publish a blog post via RabbitWrite.naver.

        Handles token, editorId, editorSource automatically.

        Args:
            title: Post title.
            components: SE editor components (from html_to_components or manual).
            category_no: Category number (0 = default).
            tags: Comma-separated tags.
            open_type: 0=private, 2=public.

        Returns:
            {"success": bool, "url": str|None, "logNo": str, "raw": dict}
        """
        if not self.blog_id:
            self.init_blog()

        # Get editor info (token + editorId + editorSource)
        info = self.get_editor_info(category_no)

        # Build title component (viruagent-cli structure)
        title_component = {
            "id": _se_id(),
            "layout": "default",
            "title": [{
                "id": _se_id(),
                "nodes": [{
                    "id": _se_id(),
                    "value": title,
                    "@ctype": "textNode",
                }],
                "@ctype": "paragraph",
            }],
            "subTitle": None,
            "align": "left",
            "@ctype": "documentTitle",
        }

        document_model = {
            "documentId": "",
            "document": {
                "version": "2.9.0",
                "theme": "default",
                "language": "ko-KR",
                "id": info["editor_id"],
                "components": [title_component] + components,
            },
        }

        population_params = {
            "configuration": {
                "openType": open_type,
                "commentYn": True,
                "searchYn": True,
                "sympathyYn": True,
                "scrapType": 2,
                "outSideAllowYn": True,
                "twitterPostingYn": False,
                "facebookPostingYn": False,
                "cclYn": False,
            },
            "populationMeta": {
                "categoryId": str(category_no),
                "logNo": None,
                "directorySeq": 0,
                "directoryDetail": None,
                "mrBlogTalkCode": None,
                "postWriteTimeType": "now",
                "tags": tags,
                "moviePanelParticipation": False,
                "greenReviewBannerYn": False,
                "continueSaved": False,
                "noticePostYn": False,
                "autoByCategoryYn": False,
                "postLocationSupportYn": False,
                "postLocationJson": None,
                "prePostDate": None,
                "thisDayPostInfo": None,
                "scrapYn": False,
            },
            "editorSource": info["editor_source"],
        }

        doc_json = json.dumps(document_model, ensure_ascii=False, separators=(",", ":"))
        pop_json = json.dumps(population_params, ensure_ascii=False, separators=(",", ":"))
        referer = self._referer(category_no, "Redirect=Write")

        # Use stealth_browser for RabbitWrite (requests gets "invalid parameter")
        from naver_blog.browser import BrowserSession

        with BrowserSession() as browser:
            result = browser.publish(self.blog_id, doc_json, pop_json, referer)

        if not result.get("isSuccess"):
            return {"success": False, "url": None, "logNo": "", "raw": result}

        redirect_url = result.get("result", {}).get("redirectUrl", "")
        log_no_match = re.search(r"logNo=(\d+)", redirect_url)
        log_no = log_no_match.group(1) if log_no_match else ""
        post_url = f"https://blog.naver.com/{self.blog_id}/{log_no}" if log_no else None

        return {"success": True, "url": post_url, "logNo": log_no, "raw": result}

    # ── Posts listing ───────────────────────────────────────────

    def list_posts(self, limit: int = 10) -> list[dict]:
        """Get recent blog posts."""
        if not self.blog_id:
            self.init_blog()
        resp = self._get(
            f"{BLOG_HOST}/PostTitleListAsync.naver"
            f"?blogId={self.blog_id}&viewdate=&currentPage=1&countPerPage={limit}",
            headers={"Referer": f"{BLOG_HOST}/{self.blog_id}"},
        )
        text = resp.text.replace("\\'", "'")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        return data.get("postList", [])
