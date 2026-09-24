from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hesperan_client import HesperanError, post


class ReportOutcomeTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        decision_id = str(tool_parameters.get("decision_id") or "").strip()
        actual = str(tool_parameters.get("actual") or "").strip()
        if not decision_id or not actual:
            raise HesperanError("Decision ID and correct answer are required.")
        body, _ = post(
            self.runtime.credentials["hesperan_api_key"],
            "/v1/outcomes",
            {"decision_id": decision_id, "actual": actual},
        )
        result = {
            "ok": body.get("ok") is True,
            "duplicate": body.get("duplicate") is True,
            "decision_id": decision_id,
            "actual": actual,
        }
        yield self.create_json_message(result)
        for name, value in result.items():
            yield self.create_variable_message(name, value)
