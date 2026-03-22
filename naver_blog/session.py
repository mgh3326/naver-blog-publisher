"""Cookie persistence and requests session creation."""

import json
from pathlib import Path

import requests

NAVER_COOKIE_DOMAINS = [
    "https://www.naver.com",
    "https://nid.naver.com",
    "https://blog.naver.com",
]

DEFAULT_SESSION_PATH = "~/.naver-blog/session.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

REQUIRED_COOKIES = ("NID_AUT", "NID_SES")


class SessionError(Exception):
    """Raised on session load/validation errors."""


async def save_cookies(context, session_path: Path) -> None:
    """Extract cookies from Playwright context and save as JSON.

    Playwright's context.cookies() can access httpOnly cookies.
    """
    all_cookies = []
    seen = set()

    for domain_url in NAVER_COOKIE_DOMAINS:
        cookies = await context.cookies(domain_url)
        for cookie in cookies:
            key = (cookie["name"], cookie.get("domain", ""))
            if key not in seen:
                seen.add(key)
                all_cookies.append(cookie)

    session_path = Path(session_path).expanduser()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(all_cookies, indent=2, ensure_ascii=False))


def load_session(session_path: str = DEFAULT_SESSION_PATH) -> requests.Session:
    """Load cookies from JSON and return a configured requests.Session.

    Raises SessionError if required cookies are missing.
    """
    path = Path(session_path).expanduser()
    if not path.exists():
        raise SessionError(f"Session file not found: {path}. Run 'naver-blog login' first.")

    cookies_data = json.loads(path.read_text())

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    cookie_names = set()
    for cookie in cookies_data:
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain", ".naver.com"),
            path=cookie.get("path", "/"),
        )
        cookie_names.add(cookie["name"])

    missing = [name for name in REQUIRED_COOKIES if name not in cookie_names]
    if missing:
        raise SessionError(f"Required cookies missing: {', '.join(missing)}. Re-login needed.")

    return session


def validate_session(session_path: str = DEFAULT_SESSION_PATH) -> bool:
    """Check if saved session is still valid by accessing MyBlog.naver."""
    try:
        session = load_session(session_path)
    except SessionError:
        return False

    try:
        resp = session.get(
            "https://blog.naver.com/MyBlog.naver",
            headers={"Referer": "https://blog.naver.com/"},
            allow_redirects=False,
            timeout=10,
        )
        # If redirected to login, session is invalid
        if resp.status_code in (301, 302):
            location = resp.headers.get("Location", "")
            if "login" in location.lower():
                return False
        # If response contains login indicators, invalid
        if resp.status_code == 200:
            text = resp.text[:2000]
            if "blogId" in text:
                return True
        return False
    except requests.RequestException:
        return False
