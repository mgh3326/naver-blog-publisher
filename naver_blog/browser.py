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

    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout_sec)
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


def browser_post_form(instance_id: str, url: str, form_data: dict, referer: str | None = None) -> dict:
    """POST URL-encoded form data via browser fetch(), return JSON response."""
    escaped_json = json.dumps(form_data).replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    referer_header = f"'Referer': '{referer}'," if referer else ""

    script = f"""
    (function() {{
        var data = JSON.parse(`{escaped_json}`);
        var params = new URLSearchParams();
        for (var key in data) {{ params.append(key, data[key]); }}
        
        fetch('{url}', {{
            method: 'POST',
            credentials: 'include',
            headers: {{
                'Content-Type': 'application/x-www-form-urlencoded',
                {referer_header}
            }},
            body: params.toString()
        }}).then(r => r.json()).then(j => {{
            document.title = '__RESULT__' + JSON.stringify(j);
        }}).catch(e => {{
            document.title = '__ERROR__' + e.message;
        }})
    }})()
    """
    _mcporter_call("execute_script", instance_id=instance_id, script=script)
    result_str = _poll_title(instance_id, max_wait=30)
    return json.loads(result_str)


class BrowserSession:
    """Manages a stealth_browser instance for publish operations."""

    def __init__(self, profile_dir: str = NAVER_BLOG_PROFILE):
        self.profile_dir = profile_dir
        self.instance_id: str | None = None

    def start(self) -> str:
        """Spawn browser and navigate to blog."""
        # Close any existing instances first
        try:
            instances = _mcporter_call("list_instances")
            if isinstance(instances, list):
                for inst in instances:
                    _mcporter_call("close_instance", instance_id=inst["instance_id"])
        except Exception:
            pass

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
        """Close browser instance."""
        if self.instance_id:
            try:
                _mcporter_call("close_instance", instance_id=self.instance_id)
            except Exception:
                pass
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
