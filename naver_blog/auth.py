"""Playwright-based Naver login with anti-detection."""

import asyncio
import json
import os
from pathlib import Path

ANTI_DETECTION_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
window.chrome = { runtime: {} };
"""

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com"
LOGIN_SUCCESS_INDICATORS = ["www.naver.com", "naver.com/notice/read"]
MANUAL_LOGIN_TIMEOUT_MS = 300_000  # 5 minutes

NAVER_COOKIE_DOMAINS = [
    "https://www.naver.com",
    "https://nid.naver.com",
    "https://blog.naver.com",
]


class LoginError(Exception):
    """Raised when login fails."""


async def login(
    username: str | None = None,
    password: str | None = None,
    manual: bool = False,
    session_path: str = "~/.naver-blog/session.json",
) -> Path:
    """Log in to Naver via Playwright and save cookies.

    Args:
        username: Naver ID. Falls back to NAVER_USERNAME env var.
        password: Naver password. Falls back to NAVER_PASSWORD env var.
        manual: If True, open browser for manual login (QR, etc.).
        session_path: Where to save cookies JSON.

    Returns:
        Path to the saved session file.
    """
    from playwright.async_api import async_playwright

    session_file = Path(session_path).expanduser()
    session_file.parent.mkdir(parents=True, exist_ok=True)

    headless = not manual
    if not manual:
        username = username or os.environ.get("NAVER_USERNAME")
        password = password or os.environ.get("NAVER_PASSWORD")
        if not username or not password:
            raise LoginError(
                "Username and password required for auto login. "
                "Set NAVER_USERNAME/NAVER_PASSWORD or use --manual."
            )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        page = await context.new_page()
        await page.add_init_script(ANTI_DETECTION_SCRIPT)
        await page.goto(NAVER_LOGIN_URL, wait_until="networkidle")

        if manual:
            print("🔑 브라우저에서 직접 로그인하세요 (5분 타임아웃)...")
            try:
                await page.wait_for_url(
                    lambda url: any(ind in url for ind in LOGIN_SUCCESS_INDICATORS),
                    timeout=MANUAL_LOGIN_TIMEOUT_MS,
                )
            except Exception as exc:
                raise LoginError("Manual login timed out.") from exc
        else:
            # Inject credentials via JS to avoid bot detection
            await page.evaluate(
                "(id) => { const el = document.getElementById('id'); if (el) el.value = id; }",
                username,
            )
            await page.evaluate(
                "(pw) => { const el = document.getElementById('pw'); if (el) el.value = pw; }",
                password,
            )

            # Check "keep me logged in"
            keep_check = await page.query_selector("#keep")
            if keep_check:
                await keep_check.click()

            # Click login button
            login_btn = await page.query_selector("#log\\.login")
            if login_btn:
                await login_btn.click()
            else:
                raise LoginError("Login button not found.")

            # Wait for navigation
            try:
                await page.wait_for_url(
                    lambda url: any(ind in url for ind in LOGIN_SUCCESS_INDICATORS),
                    timeout=15_000,
                )
            except Exception:
                # Check for known error states
                content = await page.content()
                if "캡차" in content or "captcha" in content.lower():
                    raise LoginError("CAPTCHA detected. Use --manual mode.")
                if "2차 인증" in content or "이중 인증" in content:
                    raise LoginError("2FA required. Use --manual mode.")
                if "비밀번호가 틀렸" in content or "비밀번호를 확인" in content:
                    raise LoginError("Incorrect password.")
                if "해외 로그인" in content or "지역" in content:
                    raise LoginError("Region block detected. Use --manual mode.")
                raise LoginError("Login failed. Check credentials or use --manual mode.")

        # Verify NID_AUT cookie exists
        cookies = await context.cookies()
        nid_aut = [c for c in cookies if c["name"] == "NID_AUT"]
        if not nid_aut:
            raise LoginError("Login succeeded in navigation but NID_AUT cookie not found.")

        # Save cookies from all Naver domains
        from naver_blog.session import save_cookies

        await save_cookies(context, session_file)

        await browser.close()

    print(f"✅ 로그인 성공! 세션 저장: {session_file}")
    return session_file
