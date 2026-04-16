from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict


def fetch_json(url: str, *, timeout: float = 25.0) -> Dict[str, Any]:
    """
    GET JSON with a browser-like User-Agent.

    If HTTPS verification fails in some dev environments, set env
    ``PLAYCALLER_HTTP_INSECURE_SSL=1`` (not recommended for production).
    """
    req = urllib.request.Request(url, headers={"User-Agent": "playcaller/1.0 (+https://github.com)"})
    ctx = None
    if os.environ.get("PLAYCALLER_HTTP_INSECURE_SSL") == "1":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e
    try:
        out = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from {url}: {e}") from e
    if not isinstance(out, dict):
        raise RuntimeError("Expected JSON object at root")
    return out
