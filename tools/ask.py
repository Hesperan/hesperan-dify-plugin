from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hesperan_client import as_bool, parse_state, post
from tools.questions import QUESTION_NAME, build_question, flatten_answer


class AskTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        question = build_question(
            tool_parameters.get("question_type", "choice"),
            tool_parameters.get("question", ""),
            tool_parameters.get("options"),
        )
        state = parse_state(tool_parameters.get("state"), as_bool(tool_parameters.get("state_is_json", False)))
        body, _ = post(
            self.runtime.credentials["hesperan_api_key"],
            "/v1/systemone",
            {"state": state, "questions": {QUESTION_NAME: question}},
        )
        result = flatten_answer(body)
        yield self.create_json_message(result)
        for name, value in result.items():
            yield self.create_variable_message(name, value)
