"""Small HTTP client for the Hesperan API (https://api.hesperan.com).

Every error is turned into a message that says whether anything was charged and
whether retrying helps. The API key is only ever sent as a bearer token to the
fixed Hesperan host and never included in error messages.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import httpx

BASE_URL = "https://api.hesperan.com"
REQUEST_TIMEOUT = httpx.Timeout(100.0, connect=10.0)
LOOKUP_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
USER_AGENT = "hesperan-dify-plugin/0.0.1"

SLUG_RE = re.compile(r"^[a-z0-9-]{1,64}$")
IDEMPOTENCY_KEY_RE = re.compile(r"^[\x21-\x7e]{1,255}$")


class HesperanError(Exception):
    """An error with a message meant for the person or agent using the tool."""


def _headers(api_key: str, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    if extra:
        headers.update(extra)
    return headers


def _error_text(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:300] or None
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        return body["error"]
    return None


def describe_error(status: int, message: str | None) -> str:
    detail = f": {message}" if message else ""
    if status == 400:
        return f"Hesperan rejected the request{detail}. Fix the input; retrying it unchanged will fail again."
    if status == 401:
        return "The Hesperan API key is missing, unknown or revoked. Update the key in the plugin settings."
    if status == 402:
        return (
            f"Hesperan could not bill this request{detail}. Nothing was charged. "
            "Top up your balance or subscribe to Pro in the Hesperan console (Billing), then run again."
        )
    if status == 404:
        return f"Hesperan did not find it{detail}. Check the profile slug or decision ID."
    if status == 409:
        return f"Hesperan refused the request{detail}."
    if status == 413:
        return "The request is larger than 256 KB. Send less state."
    if status == 429:
        return "Hesperan rate limit exceeded. Nothing was charged. Retry after a short wait."
    if status == 502:
        return (
            "The Hesperan model was temporarily unavailable or answered invalidly. "
            "Nothing was charged. Retry with backoff."
        )
    if status == 503:
        if message and "opens soon" in message:
            return (
                "The Hesperan API is not live yet: no model is connected. Nothing was charged. "
                "Retrying will not help until the API opens."
            )
        return "The Hesperan model is starting. Nothing was charged. Retry in about 30 seconds."
    return f"Hesperan returned HTTP {status}{detail}."


def post(
    api_key: str,
    path: str,
    body: Mapping[str, Any],
    headers: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], httpx.Headers]:
    """POST JSON to the API and return the decoded body and the response headers."""
    try:
        response = httpx.post(
            f"{BASE_URL}{path}",
            headers=_headers(api_key, headers),
            content=json.dumps(body),
            timeout=REQUEST_TIMEOUT,
        )
    except httpx.TimeoutException as e:
        raise HesperanError(
            "Hesperan did not answer in time. Retry later; for decisions, send an idempotency key "
            "so that a retry cannot be charged twice."
        ) from e
    except httpx.HTTPError as e:
        raise HesperanError("Hesperan could not be reached. Retry later.") from e

    if response.status_code >= 400:
        raise HesperanError(describe_error(response.status_code, _error_text(response)))
    try:
        data = response.json()
    except ValueError as e:
        raise HesperanError("Hesperan returned a response that is not JSON.") from e
    if not isinstance(data, dict):
        raise HesperanError("Hesperan returned an unexpected response.")
    return data, response.headers


def _get(api_key: str, path: str) -> httpx.Response:
    try:
        response = httpx.get(f"{BASE_URL}{path}", headers=_headers(api_key), timeout=LOOKUP_TIMEOUT)
    except httpx.HTTPError as e:
        raise HesperanError("Hesperan could not be reached. Try again in a moment.") from e
    return response


def validate_key(api_key: str) -> None:
    """Raise HesperanError unless the key is accepted.

    Uses the free GET /v1/me: no model call and nothing charged, so it also works before the API opens.
    """
    key = (api_key or "").strip()
    if not key.startswith("hsp_"):
        raise HesperanError("Hesperan API keys start with hsp_.")
    response = _get(key, "/v1/me")
    if response.status_code == 200:
        return
    if response.status_code == 401:
        raise HesperanError("This API key is unknown or revoked. Create a new key in the Hesperan console.")
    raise HesperanError(f"Hesperan could not check the key (HTTP {response.status_code}). Try again in a moment.")


def list_profiles(api_key: str) -> list[dict[str, Any]]:
    """The account's decision profiles from the free GET /v1/profiles."""
    response = _get(api_key, "/v1/profiles")
    if response.status_code >= 400:
        raise HesperanError(describe_error(response.status_code, _error_text(response)))
    try:
        profiles = response.json().get("profiles")
    except (ValueError, AttributeError) as e:
        raise HesperanError("Hesperan returned an unexpected response.") from e
    if not isinstance(profiles, list):
        return []
    return [p for p in profiles if isinstance(p, dict) and isinstance(p.get("slug"), str)]


def profile_label(profile: Mapping[str, Any]) -> str:
    """Name and slug; profiles without a successful calibration are marked, since they cannot decide yet."""
    slug = profile["slug"]
    label = f"{profile.get('name') or slug} ({slug})"
    return label if profile.get("calibrated") else f"{label} - not calibrated yet"


def parse_state(state: Any, as_json: bool) -> Any:
    """Return the state to send: text as-is, or a parsed JSON object/array."""
    if isinstance(state, (dict, list)):
        return state
    text = "" if state is None else str(state)
    if not as_json:
        if not text.strip():
            raise HesperanError("State must not be empty.")
        return text
    try:
        parsed = json.loads(text)
    except ValueError as e:
        raise HesperanError(
            "State is marked as JSON but could not be parsed. Pass a JSON object or array, or turn off 'State is JSON'."
        ) from e
    if not isinstance(parsed, (dict, list)):
        raise HesperanError("State is marked as JSON but is not a JSON object or array.")
    return parsed


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)
