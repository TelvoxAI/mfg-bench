"""Amazon Bedrock provider for the generator (IND-982).

Any Converse-API model on Bedrock, so the corpus can be generated and judged with a
non-Claude model on the account we already pay for — the defaults are OpenAI's
open-weight `gpt-oss-120b` (main) and `gpt-oss-20b` (cheap). Claude is deliberately
NOT the default here: every system under test is Claude, so it must not write or grade
the benchmark.

Auth: `AWS_BEARER_TOKEN_BEDROCK` + `AWS_REGION` (boto3 ≥ 1.39 reads the bearer key from
the environment), or any standard AWS credential chain.

Env: LLM_PROVIDER=bedrock, LLM_MODEL_NAME=openai.gpt-oss-120b-1:0,
     CHEAP_LLM_MODEL_NAME=openai.gpt-oss-20b-1:0
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from typing import Any

from src.llm.interface import LLMInterface, Message, ReasoningLevel, ToolCall

LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "openai.gpt-oss-120b-1:0")
CHEAP_LLM_MODEL_NAME = os.environ.get("CHEAP_LLM_MODEL_NAME", "openai.gpt-oss-20b-1:0")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
_TOOL_NAME_RE = __import__("re").compile(r"[^a-zA-Z0-9_-]")


USAGE_LOG = os.environ.get(
    "BEDROCK_USAGE_LOG", os.path.join("generation_cache", "bedrock_usage.jsonl")
)
_USAGE_LOCK = __import__("threading").Lock()


def _record_usage(model: str, usage: dict) -> None:
    try:
        line = json.dumps(
            {
                "ts": __import__("time").time(),
                "model": model,
                "input_tokens": int(usage.get("inputTokens", 0) or 0),
                "output_tokens": int(usage.get("outputTokens", 0) or 0),
                "cache_read_tokens": int(usage.get("cacheReadInputTokens", 0) or 0),
            }
        )
        with _USAGE_LOCK:
            os.makedirs(os.path.dirname(USAGE_LOG) or ".", exist_ok=True)
            with open(USAGE_LOG, "a") as f:
                f.write(line + "\n")
    except OSError:
        pass


class BedrockLLM(LLMInterface):
    """Streaming Converse API client with tool use."""

    def __init__(
        self,
        model: str | None = None,
        tools: list[dict] | None = None,
        quiet: bool = False,
        reasoning_level: ReasoningLevel = "medium",
        region: str | None = None,
        client: Any = None,
    ):
        import boto3

        self.model = model or LLM_MODEL_NAME
        self.tools = self._convert_tools(tools) if tools else None
        self.quiet = quiet
        self.reasoning_level = reasoning_level
        self.client = client or boto3.client(
            "bedrock-runtime", region_name=region or AWS_REGION
        )

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """OpenAI (Responses) tool format → Bedrock toolSpec."""
        out = []
        for t in tools:
            if t.get("type") == "function":
                out.append(
                    {
                        "toolSpec": {
                            "name": t["name"],
                            "description": t.get("description", "") or t["name"],
                            "inputSchema": {
                                "json": t.get(
                                    "parameters", {"type": "object", "properties": {}}
                                )
                            },
                        }
                    }
                )
        return out

    @staticmethod
    def _build_messages(
        messages: list[Message], with_tools: bool = True
    ) -> tuple[list[dict], list[dict]]:
        system: list[dict] = []
        out: list[dict] = []

        def push(role: str, block: dict) -> None:
            # Converse requires alternating roles: merge consecutive same-role turns
            if out and out[-1]["role"] == role:
                out[-1]["content"].append(block)
            else:
                out.append({"role": role, "content": [block]})

        for m in messages:
            if m.role == "system":
                system.append({"text": m.content})
            elif m.role == "user":
                push("user", {"text": m.content})
            elif m.role == "assistant":
                if m.content:
                    push("assistant", {"text": m.content})
            elif m.role == "tool_call" and m.tool_call:
                # Converse refuses toolUse blocks without a toolConfig (a later call
                # with tools=None over a history that has them) and tool names outside
                # [a-zA-Z0-9_-]; both are replayed as plain text instead.
                name = _TOOL_NAME_RE.sub("_", m.tool_call.name or "tool")
                if with_tools:
                    push(
                        "assistant",
                        {
                            "toolUse": {
                                "toolUseId": m.tool_call.call_id,
                                "name": name,
                                "input": m.tool_call.args,
                            }
                        },
                    )
                else:
                    push(
                        "assistant",
                        {
                            "text": f"[called tool {name} with {json.dumps(m.tool_call.args)[:2000]}]"
                        },
                    )
            elif m.role == "tool_result" and m.call_id:
                if with_tools:
                    push(
                        "user",
                        {
                            "toolResult": {
                                "toolUseId": m.call_id,
                                "content": [{"text": m.content or "(empty)"}],
                            }
                        },
                    )
                else:
                    push("user", {"text": f"[tool result]\n{m.content or '(empty)'}"})
        if not out and system:
            out.append({"role": "user", "content": [{"text": system[0]["text"]}]})
            system = []
        return system, out

    def _extra_fields(self) -> dict | None:
        if self.reasoning_level and self.model.startswith("openai."):
            return {"reasoning_effort": self.reasoning_level}
        return None

    def generate(
        self, messages: list[Message]
    ) -> Generator[str | ToolCall, None, None]:
        if not self.quiet:
            print("Waiting on LLM...", flush=True)
        system, conv = self._build_messages(messages, with_tools=bool(self.tools))
        kwargs: dict[str, Any] = {
            "modelId": self.model,
            "messages": conv,
            "inferenceConfig": {"maxTokens": 16000, "temperature": 1.0},
        }
        if system:
            kwargs["system"] = system
        if self.tools:
            kwargs["toolConfig"] = {"tools": self.tools}
        extra = self._extra_fields()
        if extra:
            kwargs["additionalModelRequestFields"] = extra

        tool_calls: list[ToolCall] = []
        current: dict[str, Any] | None = None
        try:
            resp = self.client.converse_stream(**kwargs)
        except self.client.exceptions.ValidationException as e:
            # some models (Kimi K3) refuse `temperature`; retry once without it
            if "temperature" not in str(e):
                raise
            kwargs["inferenceConfig"].pop("temperature", None)
            resp = self.client.converse_stream(**kwargs)
        for event in resp["stream"]:
            if "contentBlockStart" in event:
                tu = event["contentBlockStart"].get("start", {}).get("toolUse")
                if tu:
                    current = {"id": tu["toolUseId"], "name": tu["name"], "input": ""}
                    if not self.quiet:
                        yield f"\n[Tool Call: {tu['name']}]\n"
            elif "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    yield delta["text"]
                elif "toolUse" in delta and current is not None:
                    current["input"] += delta["toolUse"].get("input", "")
                    if not self.quiet:
                        yield delta["toolUse"].get("input", "")
                elif "reasoningContent" in delta and not self.quiet:
                    print(delta["reasoningContent"].get("text", ""), end="", flush=True)
            elif "contentBlockStop" in event and current is not None:
                if not self.quiet:
                    yield "\n[/Tool Call]\n"
                try:
                    args = json.loads(current["input"]) if current["input"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    ToolCall(name=current["name"], args=args, call_id=current["id"])
                )
                current = None
            elif "metadata" in event:
                # token accounting: one line per call, so cost per document can be
                # computed from generation_cache/bedrock_usage.jsonl (IND-982 RUNLOG)
                _record_usage(self.model, event["metadata"].get("usage") or {})
            # keep reading until the stream is exhausted: breaking early leaves the
            # urllib3 generator to be closed by the GC with a noisy ValueError
        for tc in tool_calls:
            yield tc
