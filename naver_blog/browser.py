"""Stealth browser integration for RabbitWrite API.

Uses mcporter + stealth_browser MCP to execute fetch() inside a real browser
context, bypassing Naver's anti-bot checks on the publish endpoint.
"""

import json
import subprocess
import time

MCPORTER = "mcporter"
NAVER_BLOG_PROFILE = "/home/mgh3326/.stealth-browser/naver-blog-profile"


class BrowserError(Exception):
    """Raised on browser operation failures."""


def _mcporter_call(tool: str, timeout_sec: int = 120, **kwargs) -> dict | None:
    """Call a stealth_browser MCP tool via mcporter."""
    args = [MCPORTER, "call", f"stealth_browser.{tool}"]
    for k, v in kwargs.items():
        if isinstance(v, bool):
            args.append(f"{k}={'true' if v else 'false'}")
        else:
            args.append(f"{k}={v}")

    env = {**subprocess.os.environ}
    mcporter_config = subprocess.os.environ.get("MCPORTER_CONFIG")
    if mcporter_config:
        env["MCPORTER_CONFIG"] = mcporter_config
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout_sec, env=env)
    if result.returncode != 0:
        raise BrowserError(f"mcporter error: {result.stderr[:500]}")
    if not result.stdout.strip():
        raise BrowserError(f"mcporter returned empty output for {tool}")
    return json.loads(result.stdout)


def _poll_title(instance_id: str, max_wait: int = 30) -> str:
    """Poll document.title for __RESULT__ or __ERROR__ prefix."""
    for _ in range(max_wait * 2):
        time.sleep(0.5)
        res = _mcporter_call(
            "execute_script",
            instance_id=instance_id,
            script="(function(){ return document.title; })()",
        )
        title = res.get("result", "")
        if title.startswith("__RESULT__"):
            return title[10:]
        if title.startswith("__ERROR__"):
            raise BrowserError(f"Browser fetch error: {title[9:]}")
    raise TimeoutError("Browser fetch timed out")


def _store_text_in_browser(instance_id: str, element_id: str, text: str) -> None:
    """Store a large text string in a hidden textarea in the browser.

    Uses base64 encoding to avoid JS string escaping issues with quotes,
    backslashes, and unicode characters in JSON payloads.
    """
    import base64

    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")

    chunk_size = 200000
    chunks = [b64[i:i + chunk_size] for i in range(0, len(b64), chunk_size)]

    # First chunk — create element and store b64
    _mcporter_call(
        "execute_script",
        instance_id=instance_id,
        script=f"(function(){{ var el = document.getElementById('{element_id}'); if(!el){{ el = document.createElement('textarea'); el.id='{element_id}'; el.style.display='none'; document.body.appendChild(el); }} el.dataset.b64 = '{chunks[0]}'; return 'ok'; }})()",
    )

    for chunk in chunks[1:]:
        _mcporter_call(
            "execute_script",
            instance_id=instance_id,
            script=f"(function(){{ document.getElementById('{element_id}').dataset.b64 += '{chunk}'; return 'ok'; }})()",
        )

    # Decode base64 → utf-8 text and store in .value
    _mcporter_call(
        "execute_script",
        instance_id=instance_id,
        script=f"(function(){{ var el = document.getElementById('{element_id}'); el.value = decodeURIComponent(atob(el.dataset.b64).split('').map(function(c){{ return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2); }}).join('')); return el.value.length; }})()",
    )


def browser_post_form(instance_id: str, url: str, form_data: dict, referer: str | None = None) -> dict:
    """POST URL-encoded form data via browser fetch(), return JSON response.

    Stores each form field in hidden textareas, then builds URLSearchParams
    in JS (matching the exact encoding that worked in browser console).
    """
    # Store each form field in separate hidden textareas
    field_ids = []
    for key, value in form_data.items():
        elem_id = f"__pub_{key}"
        _store_text_in_browser(instance_id, elem_id, value)
        field_ids.append((key, elem_id))

    # Build JS that reads from textareas and creates URLSearchParams
    read_parts = []
    for key, elem_id in field_ids:
        read_parts.append(f"params.append('{key}', document.getElementById('{elem_id}').value);")
    params_js = "\n        ".join(read_parts)

    referer_header = f"'Referer': '{referer}'," if referer else ""

    fetch_script = f"""
    (function() {{
        var params = new URLSearchParams();
        {params_js}
        
        fetch('{url}', {{
            method: 'POST',
            credentials: 'include',
            headers: {{
                'Content-Type': 'application/x-www-form-urlencoded',
                {referer_header}
            }},
            body: params.toString()
        }}).then(function(r) {{ return r.json(); }}).then(function(j) {{
            document.title = '__RESULT__' + JSON.stringify(j);
        }}).catch(function(e) {{
            document.title = '__ERROR__' + e.message;
        }});
    }})()
    """
    _mcporter_call("execute_script", instance_id=instance_id, script=fetch_script)
    result_str = _poll_title(instance_id, max_wait=30)
    return json.loads(result_str)


class BrowserSession:
    """Manages a stealth_browser instance for publish operations."""

    def __init__(self, profile_dir: str = NAVER_BLOG_PROFILE):
        self.profile_dir = profile_dir
        self.instance_id: str | None = None

    def start(self) -> str:
        """Reuse existing browser instance or spawn a new one."""
        # Try to reuse an existing instance (preserves QR login session)
        try:
            instances = _mcporter_call("list_instances")
            # list_instances may return a list or a dict with 'result'
            if isinstance(instances, dict):
                instances = instances.get("result", [])
            if isinstance(instances, list) and instances:
                self.instance_id = instances[0]["instance_id"]
                # Verify it's alive
                _mcporter_call(
                    "execute_script",
                    instance_id=self.instance_id,
                    script="(function(){ return 'ok'; })()",
                )
                # Navigate to blog domain for cookie scope
                _mcporter_call(
                    "navigate",
                    instance_id=self.instance_id,
                    url="https://blog.naver.com/mgh3326",
                )
                time.sleep(2)
                return self.instance_id
        except Exception:
            pass

        # No existing instance — spawn new one
        result = _mcporter_call(
            "spawn_browser",
            headless=False,
            user_data_dir=self.profile_dir,
        )
        self.instance_id = result["instance_id"]

        # Navigate to blog (activate cookies)
        _mcporter_call(
            "navigate",
            instance_id=self.instance_id,
            url="https://blog.naver.com/mgh3326",
        )
        time.sleep(2)
        return self.instance_id

    def close(self):
        """Detach from browser instance (keep it running for session reuse)."""
        # Don't close — keep browser alive for cookie persistence
        self.instance_id = None

    def publish(self, blog_id: str, document_model: str, population_params: str, referer: str) -> dict:
        """Call RabbitWrite.naver via browser fetch."""
        if not self.instance_id:
            self.start()

        return browser_post_form(
            self.instance_id,
            "https://blog.naver.com/RabbitWrite.naver",
            {
                "blogId": blog_id,
                "documentModel": document_model,
                "populationParams": population_params,
                "productApiVersion": "v1",
            },
            referer=referer,
        )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()
