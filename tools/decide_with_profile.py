from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from dify_plugin import Tool
from dify_plugin.entities import I18nObject, ParameterOption
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hesperan_client import (
    IDEMPOTENCY_KEY_RE,
    SLUG_RE,
    HesperanError,
    as_bool,
    list_profiles,
    parse_state,
    post,
    profile_label,
)

OUTPUT_FIELDS = (
    "decision_id",
    "profile",
    "decision",
    "confidence",
    "action",
    "threshold",
    "target_precision",
    "calibration_version",
    "probabilities",
    "raw_probabilities",
)


class DecideWithProfileTool(Tool):
    def _fetch_parameter_options(self, parameter: str) -> list[ParameterOption]:
        """Dropdown options for the `profile` parameter, listed by the free GET /v1/profiles."""
        if parameter != "profile":
            return []
        profiles = list_profiles(self.runtime.credentials["hesperan_api_key"])
        options = [ParameterOption(value=p["slug"], label=I18nObject(en_US=profile_label(p))) for p in profiles]
        return options

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        profile = str(tool_parameters.get("profile") or "").strip()
        if not SLUG_RE.match(profile):
            raise HesperanError(
                "Profile must be the slug of a decision profile in lowercase letters, digits and hyphens, "
                "for example ticket-routing."
            )
        key = str(tool_parameters.get("idempotency_key") or "").strip()
        if key and not IDEMPOTENCY_KEY_RE.match(key):
            raise HesperanError("Idempotency key must be 1 to 255 visible ASCII characters without spaces.")
        state = parse_state(tool_parameters.get("state"), as_bool(tool_parameters.get("state_is_json", False)))

        body, headers = post(
            self.runtime.credentials["hesperan_api_key"],
            f"/v1/decide/{quote(profile, safe='')}",
            {"state": state},
            {"Idempotency-Key": key} if key else None,
        )
        result = {name: body.get(name) for name in OUTPUT_FIELDS}
        result["automate"] = body.get("action") == "auto"
        result["replayed"] = headers.get("idempotent-replayed") == "true"
        yield self.create_json_message(result)
        for name, value in result.items():
            yield self.create_variable_message(name, value)
