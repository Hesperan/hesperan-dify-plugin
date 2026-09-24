"""Unit tests with a mocked HTTP layer. Run from the plugin directory: python -m pytest tests"""

import json

import httpx
import pytest

from provider.hesperan import HesperanProvider
from tools import hesperan_client
from tools.ask import AskTool
from tools.decide_with_profile import DecideWithProfileTool
from tools.hesperan_client import HesperanError
from tools.questions import build_question
from tools.report_outcome import ReportOutcomeTool
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

KEY = "hsp_" + "a" * 40
CREDENTIALS = {"hesperan_api_key": KEY}


class Recorder:
    def __init__(self):
        self.calls = []
        self.replies = []

    def reply(self, status, body, headers=None):
        self.replies.append((status, body, headers or {}))

    def post(self, url, headers=None, content=None, timeout=None):
        return self._record("POST", url, headers, json.loads(content), timeout)

    def get(self, url, headers=None, timeout=None):
        return self._record("GET", url, headers, None, timeout)

    def _record(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body, "timeout": timeout})
        status, body, extra = self.replies.pop(0)
        return httpx.Response(status, json=body, headers=extra, request=httpx.Request(method, url))

    @property
    def last(self):
        return self.calls[-1]


@pytest.fixture
def api(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(hesperan_client.httpx, "post", rec.post)
    monkeypatch.setattr(hesperan_client.httpx, "get", rec.get)
    return rec


def run(tool_cls, params):
    tool = tool_cls.from_credentials(CREDENTIALS)
    messages = list(tool._invoke(params))
    json_msg = messages[0].message.json_object
    variables = {m.message.variable_name: m.message.variable_value for m in messages[1:]}
    return json_msg, variables


DECISION = {
    "decision_id": "0f6c2a4e-5b1d-4c1e-9a7f-2d3b8e6f1a90",
    "profile": "ticket-routing",
    "decision": "billing",
    "confidence": 0.9931,
    "action": "auto",
    "threshold": 0.962,
    "target_precision": 0.99,
    "calibration_version": 1,
    "probabilities": {"billing": 0.9931, "shipping": 0.0069},
    "raw_probabilities": {"billing": 0.9412, "shipping": 0.0588},
}


def test_decide_posts_state_with_bearer_key_and_idempotency_key(api):
    api.reply(200, DECISION, {"idempotent-replayed": "true"})
    out, variables = run(
        DecideWithProfileTool,
        {"profile": "ticket-routing", "state": "I was charged twice.", "idempotency_key": "ticket-4812"},
    )
    assert api.last["url"] == "https://api.hesperan.com/v1/decide/ticket-routing"
    assert api.last["headers"]["Authorization"] == f"Bearer {KEY}"
    assert api.last["headers"]["Idempotency-Key"] == "ticket-4812"
    assert api.last["body"] == {"state": "I was charged twice."}
    assert out["decision"] == "billing" and out["automate"] is True and out["replayed"] is True
    assert variables == out


def test_decide_sends_json_state_and_no_key_header_by_default(api):
    api.reply(200, {**DECISION, "action": "review"})
    out, _ = run(
        DecideWithProfileTool,
        {"profile": "ticket-routing", "state": '{"message": "Still waiting"}', "state_is_json": True},
    )
    assert api.last["body"] == {"state": {"message": "Still waiting"}}
    assert "Idempotency-Key" not in api.last["headers"]
    assert out["automate"] is False and out["replayed"] is False


@pytest.mark.parametrize(
    "params, message",
    [
        ({"profile": "Ticket Routing", "state": "x"}, "slug"),
        ({"profile": "ticket-routing", "state": "x", "idempotency_key": "has space"}, "Idempotency key"),
        ({"profile": "ticket-routing", "state": "not json", "state_is_json": True}, "could not be parsed"),
        ({"profile": "ticket-routing", "state": "  "}, "must not be empty"),
    ],
)
def test_decide_rejects_bad_input_without_a_request(api, params, message):
    with pytest.raises(HesperanError, match=message):
        run(DecideWithProfileTool, params)
    assert api.calls == []


def test_opens_soon_is_explained_as_not_retryable(api):
    api.reply(503, {"error": "the Hesperan API opens soon — no model is connected yet; nothing was charged"})
    with pytest.raises(HesperanError, match="not live yet.*Retrying will not help"):
        run(DecideWithProfileTool, {"profile": "ticket-routing", "state": "x"})


def test_billing_error_says_nothing_was_charged(api):
    api.reply(402, {"error": "your 1M free tokens this month are used up and your balance does not cover the rest — top up your balance (pay as you go, $0.25 per 1M input tokens) or subscribe to Pro"})
    with pytest.raises(HesperanError, match="1M free tokens.*Nothing was charged.*subscribe to Pro"):
        run(AskTool, {"state": "x", "question_type": "yes_no", "question": "A statement."})


def test_ask_choice_builds_question_and_flattens_answer(api):
    api.reply(
        200,
        {
            "model": "hesperan-1",
            "answers": {"answer": {"type": "choice", "choice": "negative", "probabilities": {"positive": 0.04, "negative": 0.96}}},
            "usage": {"input_tokens": 42},
            "timing_ms": 10,
        },
    )
    out, variables = run(
        AskTool,
        {
            "state": "Never again.",
            "question_type": "choice",
            "question": "What is the tone?",
            "options": "positive: praises the product\nnegative",
        },
    )
    assert api.last["url"] == "https://api.hesperan.com/v1/systemone"
    assert api.last["body"] == {
        "state": "Never again.",
        "questions": {
            "answer": {
                "type": "choice",
                "instructions": "What is the tone?",
                "criteria": {"positive": "praises the product", "negative": ""},
            }
        },
    }
    assert out == {
        "question_type": "choice",
        "answer": "negative",
        "probability": 0.96,
        "probabilities": {"positive": 0.04, "negative": 0.96},
        "model": "hesperan-1",
        "input_tokens": 42,
    }
    assert variables == out


def test_ask_yes_no_and_score(api):
    api.reply(200, {"model": "hesperan-1", "answers": {"answer": {"type": "noul", "noul": 0.97}}, "usage": {"input_tokens": 9}, "timing_ms": 1})
    out, _ = run(
        AskTool,
        {"state": "Verify your password here", "question_type": "yes_no", "question": "This email is phishing.", "options": "no: a legitimate message"},
    )
    assert api.last["body"]["questions"]["answer"] == {
        "type": "noul",
        "instructions": "This email is phishing.",
        "criteria": {"false": "a legitimate message"},
    }
    assert out["answer"] == "yes" and out["probability_yes"] == 0.97 and out["probability_no"] == 0.03

    api.reply(
        200,
        {
            "model": "hesperan-1",
            "answers": {"answer": {"type": "score", "score": 2.64, "probabilities": {"0": 0.01, "1": 0.06, "2": 0.21, "3": 0.72}}},
            "usage": {"input_tokens": 30},
            "timing_ms": 1,
        },
    )
    out, _ = run(
        AskTool,
        {"state": '{"alert": "disk full"}', "state_is_json": "true", "question_type": "score", "question": "How urgent?", "options": '["none", "week", "today", "now"]'},
    )
    assert api.last["body"]["state"] == {"alert": "disk full"}
    assert api.last["body"]["questions"]["answer"]["criteria"] == ["none", "week", "today", "now"]
    assert out["score"] == 2.64 and out["most_likely_level"] == "3"


@pytest.mark.parametrize(
    "qtype, options, message",
    [
        ("choice", "only_one: x", "at least two options"),
        ("choice", "a\na", "unique"),
        ("choice", "a b: x\nc", "spaces"),
        ("choice", '{"a": 1', "could not be parsed"),
        ("score", "only", "two levels"),
        ("yes_no", "maybe: x", "yes: ..."),
        ("multi", "", "choice, yes_no or score"),
    ],
)
def test_bad_questions_are_rejected(qtype, options, message):
    with pytest.raises(HesperanError, match=message):
        build_question(qtype, "Which?", options)


def test_report_outcome(api):
    api.reply(200, {"ok": True, "duplicate": True})
    out, _ = run(ReportOutcomeTool, {"decision_id": " 0f6c ", "actual": "billing"})
    assert api.last["url"] == "https://api.hesperan.com/v1/outcomes"
    assert api.last["body"] == {"decision_id": "0f6c", "actual": "billing"}
    assert out == {"ok": True, "duplicate": True, "decision_id": "0f6c", "actual": "billing"}


def test_credentials_checked_with_the_free_me_endpoint(api):
    api.reply(200, {"ok": True, "plan": "free", "model_status": "unavailable"})
    HesperanProvider().validate_credentials({"hesperan_api_key": f" {KEY} "})
    assert api.last["method"] == "GET"
    assert api.last["url"] == "https://api.hesperan.com/v1/me"
    assert api.last["headers"]["Authorization"] == f"Bearer {KEY}"


def test_credentials_not_accepted_on_other_statuses(api):
    api.reply(500, {"error": "internal error"})
    with pytest.raises(ToolProviderCredentialValidationError, match="HTTP 500"):
        HesperanProvider().validate_credentials(CREDENTIALS)


PROFILES = {
    "profiles": [
        {"slug": "refund-check", "name": "Refund check", "type": "noul", "options": ["true", "false"], "calibrated": False},
        {"slug": "ticket-routing", "name": "Ticket routing", "type": "choice", "options": ["billing", "shipping"], "calibrated": True},
    ]
}


def test_profile_options_come_from_the_free_profiles_endpoint(api):
    api.reply(200, PROFILES)
    options = DecideWithProfileTool.from_credentials(CREDENTIALS).fetch_parameter_options("profile")
    assert api.last["method"] == "GET"
    assert api.last["url"] == "https://api.hesperan.com/v1/profiles"
    assert api.last["headers"]["Authorization"] == f"Bearer {KEY}"
    assert [(o.model_dump()["value"], o.model_dump()["label"]["en_US"]) for o in options] == [
        ("refund-check", "Refund check (refund-check) - not calibrated yet"),
        ("ticket-routing", "Ticket routing (ticket-routing)"),
    ]


def test_profile_options_explain_a_bad_key_and_ignore_other_parameters(api):
    api.reply(401, {"error": "unauthorized"})
    tool = DecideWithProfileTool.from_credentials(CREDENTIALS)
    with pytest.raises(HesperanError, match="unknown or revoked"):
        tool.fetch_parameter_options("profile")
    assert tool.fetch_parameter_options("state") == []
    assert len(api.calls) == 1


def test_credentials_invalid_for_unknown_key(api):
    api.reply(401, {"error": "unauthorized"})
    with pytest.raises(ToolProviderCredentialValidationError, match="unknown or revoked"):
        HesperanProvider().validate_credentials(CREDENTIALS)


def test_credentials_invalid_without_prefix_and_without_request(api):
    with pytest.raises(ToolProviderCredentialValidationError, match="hsp_"):
        HesperanProvider().validate_credentials({"hesperan_api_key": "sk-123"})
    assert api.calls == []
