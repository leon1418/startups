"""Shared helpers for the knowledge auto-update POC.

WHY the table handling below: the design's `locate` instructions address table ROWS
("the row whose Phase is 'Maximum session duration' — read its Timeout column").
BeautifulSoup's plain get_text() flattens a table into a run of words, which destroys
exactly the structure the instruction depends on. So tables are re-emitted as pipe rows
before the rest of the text is extracted.
"""

from __future__ import annotations

import json
import re

import boto3  # noqa: E402  (kept next to the other third-party imports)
import httpx
from bs4 import BeautifulSoup

import os as _os

# Overridable so the deployment can pin them without editing code (see infra/kb-autoupdate.yaml).
CHEAP_MODEL = _os.environ.get("KB_CHEAP_MODEL") or "global.anthropic.claude-haiku-4-5-20251001-v1:0"
STRONG_MODEL = _os.environ.get("KB_STRONG_MODEL") or "global.anthropic.claude-sonnet-5"
# Pinned, not inherited: see the note in state.py — an inherited AWS_REGION sends inference to a
# region where the chosen model may not be available.
REGION = _os.environ.get("KB_REGION") or "us-east-1"

_MAX_CHARS = 180_000
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"

_bedrock = None


def bedrock():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    return _bedrock


def fetch(url: str, timeout: float = 30.0) -> tuple[str, str | None]:
    """Return (text, error). text is '' when error is set."""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": _UA})
        if r.status_code != 200:
            return "", f"HTTP {r.status_code}"
        return html_to_text(r.text), None
    except Exception as e:  # noqa: BLE001 - a POC reports the failure rather than classifying it
        return "", f"{type(e).__name__}: {e}"


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # Replace each table with pipe-delimited rows so row/column addressing survives.
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        table.replace_with("\n[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]\n")

    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:_MAX_CHARS]


def ask_json(model: str, system: str, user: str, schema: dict, max_tokens: int = 4096) -> dict:
    """Force a structured answer via a single tool the model must call.

    temperature=0 is requested for reproducibility, but the newest models reject it
    ("`temperature` is deprecated for this model"), so fall back to omitting it.

    KB_INFERENCE=github|openai routes every call to an OpenAI-compatible endpoint instead
    of the Bedrock SDK — the no-AWS-credentials experiment. Same contract, same guards;
    only the transport differs.
    """
    if _os.environ.get("KB_INFERENCE") in ("github", "openai"):
        return _ask_json_openai_compat(model, system, user, schema, max_tokens)
    kwargs = dict(
        modelId=model,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        toolConfig={
            "tools": [{"toolSpec": {"name": "answer", "description": "Return the answer.", "inputSchema": {"json": schema}}}],
            "toolChoice": {"tool": {"name": "answer"}},
        },
    )
    try:
        resp = bedrock().converse(inferenceConfig={"maxTokens": max_tokens, "temperature": 0}, **kwargs)
    except Exception as e:  # noqa: BLE001
        if "temperature" not in str(e):
            raise
        resp = bedrock().converse(inferenceConfig={"maxTokens": max_tokens}, **kwargs)

    # A truncated generation yields a PARTIAL tool input — silently missing keys, which
    # surfaces far away as a KeyError. Fail here instead.
    if resp.get("stopReason") == "max_tokens":
        raise RuntimeError(f"output truncated at maxTokens={max_tokens}; raise it or ask for a shorter answer")

    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block:
            payload = coerce_payload(block["toolUse"]["input"], schema)
            required = schema.get("required", [])
            missing = [k for k in required if k not in payload]
            if missing and len(missing) == len(required):
                # Nothing usable came back — that is a real failure.
                raise RuntimeError(f"tool payload has no schema keys; got {list(payload)} :: {json.dumps(payload)[:800]}")
            if missing:
                # A partially-populated answer is still useful; do not throw the run away
                # over one omitted scalar. Record what was missing so it stays visible.
                empties = {"string": "", "array": [], "object": {}, "boolean": False, "integer": 0, "number": 0}
                for k in missing:
                    t = schema.get("properties", {}).get(k, {}).get("type", "string")
                    payload[k] = empties.get(t, "")
                payload["_missing_keys"] = missing
            return payload
    raise RuntimeError(f"model did not call the tool: {json.dumps(resp)[:500]}")


GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"


def _ask_json_openai_compat(model: str, system: str, user: str, schema: dict, max_tokens: int) -> dict:
    """OpenAI-compatible chat-completions backend with a forced tool call.

    KB_INFERENCE=openai talks to KB_INFERENCE_URL (a /chat/completions endpoint) with
    KB_INFERENCE_TOKEN as the bearer — any OpenAI-compatible gateway works, including a
    Bedrock access gateway, so the workflow itself needs no cloud credentials.
    KB_INFERENCE=github keeps the (retiring) GitHub Models defaults: the Actions
    GITHUB_TOKEN and a tight output clamp for its free tier. 429s wait and retry instead
    of failing the run.
    """
    import time

    github = _os.environ.get("KB_INFERENCE") == "github"
    url = _os.environ.get("KB_INFERENCE_URL") or GITHUB_MODELS_URL
    # The GITHUB_TOKEN fallback is for GitHub Models ONLY. A custom gateway must get its
    # own token — falling back would send the repo token to a third-party URL and fail
    # with a misleading 401 when the secret is simply unset.
    token = _os.environ.get("KB_INFERENCE_TOKEN") or (
        (_os.environ.get("KB_GH_MODELS_TOKEN") or _os.environ.get("GITHUB_TOKEN")) if github else None)
    if not token:
        raise RuntimeError("KB_INFERENCE_TOKEN is not set (is the repo secret configured?)")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": min(max_tokens, 4000) if github else max_tokens,
        "tools": [{"type": "function",
                   "function": {"name": "answer", "description": "Return the answer.", "parameters": schema}}],
        "tool_choice": {"type": "function", "function": {"name": "answer"}},
    }
    for attempt in range(5):
        r = httpx.post(url, json=body, timeout=180,
                       headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 429:
            wait = int(r.headers.get("retry-after", "15"))
            print(f"    [inference] rate limited, waiting {wait}s (attempt {attempt + 1}/5)")
            time.sleep(min(wait, 120))
            continue
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            raise RuntimeError(f"model did not call the tool: {str(msg)[:400]}")
        payload = coerce_payload(json.loads(calls[0]["function"]["arguments"]), schema)
        required = schema.get("required", [])
        missing = [k for k in required if k not in payload]
        if missing and len(missing) == len(required):
            raise RuntimeError(f"tool payload has no schema keys; got {list(payload)}")
        if missing:
            empties = {"string": "", "array": [], "object": {}, "boolean": False, "integer": 0, "number": 0}
            for k in missing:
                t = schema.get("properties", {}).get(k, {}).get("type", "string")
                payload[k] = empties.get(t, "")
            payload["_missing_keys"] = missing
        return payload
    raise RuntimeError("inference endpoint: still rate-limited after 5 attempts")


def coerce_payload(payload: dict, schema: dict) -> dict:
    """Undo the wrappers Bedrock tool-use sometimes produces.

    Observed in this POC, all from the same model on the same prompt shape:
      {"answer": {...}}       - wrapped in the tool's own name
      {"parameters": {...}}   - wrapped in a generic key
      {"parameter": {...}}    - ditto, singular
      {"affected": "{...}"}   - the whole object, JSON-encoded into a string
    Structured output on Bedrock needs this layer; without it 4 of 5 batches were lost.
    """
    props = set(schema.get("properties", {}))
    required = schema.get("required", [])

    def satisfied(p: dict) -> bool:
        return isinstance(p, dict) and all(k in p for k in required)

    for _ in range(3):
        if satisfied(payload):
            break
        if not isinstance(payload, dict) or len(payload) != 1:
            break
        (_, inner), = payload.items()
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except json.JSONDecodeError:
                break
        if not isinstance(inner, dict):
            break
        payload = inner

    # A schema key whose value arrived as a string where a structure was asked for.
    #
    # Two shapes seen from the same model on the same schema:
    #   "[\"a\",\"b\"]"  - JSON-encoded, parses
    #   "a, b, c"        - a plain joined string
    #
    # The second one is the dangerous case: iterating it yields one CHARACTER per item, and a
    # list of single letters looks like data. In this pipeline that turned an array of search
    # terms into 14 single characters, every one discarded as "too short", producing a confident
    # "0 affected locations" with no error anywhere. Splitting is not cosmetic — it is the
    # difference between a wrong answer and no answer.
    if isinstance(payload, dict):
        for k, v in list(payload.items()):
            want = schema.get("properties", {}).get(k, {}).get("type")
            if not isinstance(v, str) or want not in ("array", "object"):
                continue
            try:
                payload[k] = json.loads(v)
                continue
            except json.JSONDecodeError:
                pass
            if want == "array":
                parts = [p.strip().strip("\"'") for p in re.split(r"[\n;,]", v)]
                payload[k] = [p for p in parts if p]
    return payload


def load_facts(path: str = "facts.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["facts"]
