# Hesperan

**Author:** hesperan
**Version:** 0.0.1
**Type:** tool
**Source:** https://github.com/Hesperan/hesperan-dify-plugin
**Contact:** hello@hesperan.com

## Overview

[Hesperan](https://hesperan.com) is a hosted API for calibrated decisions. It answers typed questions about a text
or JSON state with probabilities, and decision profiles, calibrated on your own labelled cases, tell you for each
case whether it is safe to automate (`auto`) or should go to a person (`review`). Hesperan returns numbers and
decisions, never generated text.

This plugin adds three tools to Dify workflows, chatflows and agents:

| Tool | What it does | API |
| --- | --- | --- |
| Decide with profile | Decides one case with a calibrated profile: `decision`, `confidence`, `action` (`auto` or `review`), `decision_id` | `POST /v1/decide/{profile}` |
| Ask a question | One typed question: choice (pick an option), yes/no (probability that a statement holds) or score (rate on your levels) | `POST /v1/systemone` |
| Report outcome | Reports the correct answer for an earlier decision, so the Hesperan console can show live precision | `POST /v1/outcomes` |

## Setup

1. Create an account at https://hesperan.com and open the console.
2. Under **API keys**, create a key. It starts with `hsp_`.
3. In Dify, install the Hesperan plugin, open **Tools → Hesperan → Authorize**, and paste the key. The key is
   checked with a free request; nothing is charged and no model is called.
4. For **Decide with profile**, create and calibrate a decision profile in the console first (Profiles → New). The
   Profile field then lists your profiles by name and slug; profiles marked "not calibrated yet" cannot decide
   until their calibration succeeds.

Required credentials: one Hesperan API key. Requests are billed by input tokens to the Hesperan account of the key
(1M free tokens a month, then a prepaid balance or Pro; see https://hesperan.com/pricing); failed requests are not
charged.

## Connection requirements

The plugin connects only to `https://api.hesperan.com` over HTTPS (port 443). The Dify plugin runtime needs
outbound internet access to that host. There is no base URL to configure and no proxy setting.

## Usage

### Route a ticket in a workflow

1. Add the **Decide with profile** tool after the node that provides the ticket text.
2. Choose your profile under **Profile**, pass the ticket text as **State**, and the ticket ID as
   **Idempotency key** (retries within 24 hours then return the first decision and are not charged again).
3. Add an IF/ELSE node on the output variable `action`: `auto` continues automatically with `decision`, `review`
   goes to a person.
4. When the correct team is known, call **Report outcome** with the `decision_id` and the correct answer, one of
   the profile's answer keys (for a yes/no profile `true` or `false`).

### Ask a question

**Ask a question** takes a state, a question type, the question and options:

- **choice**: options one per line as `key: meaning`, for example

  ```
  shipping: delivery, tracking, lost parcels
  technical: bugs, crashes, login problems
  account: profile, password, email address
  ```

  Output: `answer` (the most likely key), `probability`, `probabilities`.
- **yes_no**: the question is a statement, for example `This email is a phishing attempt.` Optional options
  `yes: ...` and `no: ...` say what counts as yes and no. Output: `probability_yes`, `probability_no`, `answer`.
- **score**: options are level descriptions, one per line, lowest first. Output: `score` (expected level),
  `most_likely_level`, `probabilities`.

Turn on **State is JSON** to send a JSON object or array as structured state. Every tool returns a JSON message
and the output variables listed in its schema; agents can read the JSON directly.

## Errors

Errors say whether anything was charged and whether a retry helps. `401`: invalid key. `402`: the included tokens
are used up and the balance does not cover the rest. `404`: unknown profile or decision. `409`: the profile has no calibration yet, or an idempotency key was
reused with different input. `429` and `502`: retry later. "Model is starting" (`503`) or "did not answer in time":
the model runs on serverless GPUs and the first call after a quiet period can take about 2–3 minutes; retry a minute
later (use an idempotency key for decisions). `503` with "opens soon": the Hesperan API is closed, and retrying does
not help.

## Privacy

See [PRIVACY.md](PRIVACY.md) and https://hesperan.com/legal/privacy.

## Links

- Documentation: https://hesperan.com/docs
- API reference: https://hesperan.com/docs/api
- Decision profiles: https://hesperan.com/docs/profiles
