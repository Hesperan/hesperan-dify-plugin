"""Build one Hesperan question from tool parameters and flatten its answer."""

from __future__ import annotations

import json
import re
from typing import Any

from tools.hesperan_client import HesperanError

QUESTION_NAME = "answer"
MAX_OPTIONS = 255
QUESTION_TYPES = {"choice": "choice", "yes_no": "noul", "score": "score"}
_KEY_RE = re.compile(r"^\S+$")


def _lines(options: str) -> list[str]:
    return [line.strip() for line in options.splitlines() if line.strip()]


def _load_json(options: str) -> Any:
    try:
        return json.loads(options)
    except ValueError as e:
        raise HesperanError("Options look like JSON but could not be parsed.") from e


def choice_criteria(options: str) -> dict[str, str]:
    text = options.strip()
    if text.startswith("{"):
        data = _load_json(text)
        if not isinstance(data, dict):
            raise HesperanError("Options must be a JSON object of key to meaning.")
        pairs = [(str(k).strip(), "" if v is None else str(v).strip()) for k, v in data.items()]
    else:
        pairs = []
        for line in _lines(text):
            key, _, meaning = line.partition(":")
            pairs.append((key.strip(), meaning.strip()))
    pairs = [(k, m) for k, m in pairs if k]
    if len(pairs) < 2:
        raise HesperanError("A choice question needs at least two options, one per line as 'key: meaning'.")
    keys = [k for k, _ in pairs]
    if not all(_KEY_RE.match(k) for k in keys):
        raise HesperanError("Option keys must not contain spaces, for example billing or wrong_item.")
    if len(set(keys)) != len(keys):
        raise HesperanError("Option keys must be unique.")
    if len(keys) > MAX_OPTIONS:
        raise HesperanError(f"At most {MAX_OPTIONS} options are allowed.")
    return dict(pairs)


def score_criteria(options: str) -> list[str]:
    text = options.strip()
    if text.startswith("["):
        data = _load_json(text)
        if not isinstance(data, list):
            raise HesperanError("Levels must be a JSON array of descriptions.")
        levels = [str(v).strip() for v in data if str(v).strip()]
    else:
        levels = _lines(text)
    if len(levels) < 2:
        raise HesperanError("A score question needs at least two levels, one per line, lowest first.")
    if len(levels) > MAX_OPTIONS:
        raise HesperanError(f"At most {MAX_OPTIONS} levels are allowed.")
    return levels


def yes_no_criteria(options: str) -> dict[str, str] | None:
    criteria: dict[str, str] = {}
    for line in _lines(options):
        key, sep, meaning = line.partition(":")
        label = key.strip().lower()
        if not sep or label not in {"yes", "no"}:
            raise HesperanError("For a yes/no question, options are optional lines 'yes: ...' and 'no: ...'.")
        if meaning.strip():
            criteria["true" if label == "yes" else "false"] = meaning.strip()
    return criteria or None


def build_question(question_type: str, question: str, options: str | None) -> dict[str, Any]:
    kind = QUESTION_TYPES.get((question_type or "").strip())
    if kind is None:
        raise HesperanError("Question type must be choice, yes_no or score.")
    instructions = (question or "").strip()
    if not instructions:
        raise HesperanError("Question must not be empty.")
    opts = options or ""
    if kind == "choice":
        return {"type": "choice", "instructions": instructions, "criteria": choice_criteria(opts)}
    if kind == "score":
        return {"type": "score", "instructions": instructions, "criteria": score_criteria(opts)}
    criteria = yes_no_criteria(opts)
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if criteria:
        q["criteria"] = criteria
    return q


def _most_likely(probabilities: dict[str, float]) -> str | None:
    if not probabilities:
        return None
    return max(probabilities.items(), key=lambda kv: kv[1])[0]


def flatten_answer(response: dict[str, Any]) -> dict[str, Any]:
    answer = (response.get("answers") or {}).get(QUESTION_NAME)
    if not isinstance(answer, dict):
        raise HesperanError("Hesperan returned no answer for the question.")
    common = {
        "model": response.get("model"),
        "input_tokens": (response.get("usage") or {}).get("input_tokens"),
    }
    kind = answer.get("type")
    if kind == "choice":
        probabilities = answer.get("probabilities") or {}
        choice = answer.get("choice")
        return {
            "question_type": "choice",
            "answer": choice,
            "probability": probabilities.get(choice),
            "probabilities": probabilities,
            **common,
        }
    if kind == "noul":
        p_yes = float(answer.get("noul"))
        return {
            "question_type": "yes_no",
            "answer": "yes" if p_yes >= 0.5 else "no",
            "probability_yes": p_yes,
            "probability_no": round(1 - p_yes, 4),
            **common,
        }
    if kind == "score":
        probabilities = answer.get("probabilities") or {}
        return {
            "question_type": "score",
            "score": answer.get("score"),
            "most_likely_level": _most_likely(probabilities),
            "probabilities": probabilities,
            **common,
        }
    raise HesperanError("Hesperan returned an answer of an unknown type.")
