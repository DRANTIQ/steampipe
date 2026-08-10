"""JWT login helper for Stage 1 CLI scripts (smoke tests, schedules)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def login(stage1_url: str, email: str, password: str) -> dict[str, Any]:
    """POST /api/v1/auth/login; returns full JSON body including access_token."""
    url = f"{stage1_url.rstrip('/')}/api/v1/auth/login"
    body = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"Login failed ({exc.code}): {detail}") from exc


def bearer_headers(token: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    if extra:
        headers.update(extra)
    return headers
