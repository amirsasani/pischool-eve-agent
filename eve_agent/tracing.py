"""JSONL traces for agent requests."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.messages import RemoveMessage, ToolMessage

from eve_agent.settings import TRACE_FILE

MAX_TRACE_TOOL_OUTPUT_CHARS = 8_000
TRACE_TRUNCATION_MARKER = "\n[Trace output truncated]"


class AgentTrace:
    def __init__(self, session_id: str, message: str) -> None:
        self._started = time.perf_counter()
        self._step_starts: dict[str, float] = {}
        self._steps: dict[str, dict[str, Any]] = {}
        self._result: dict[str, Any] | None = None
        self.record: dict[str, Any] = {
            "trace_id": str(uuid4()),
            "session_id": session_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "input": message,
            "status": "running",
            "steps": [],
        }

    def observe(self, event: dict[str, Any]) -> None:
        event_type = event.get("event")
        name = event.get("name")
        run_id = event.get("run_id")
        data = event.get("data", {})

        if event_type == "on_chain_start":
            node = event.get("metadata", {}).get("langgraph_node")
            if node == name:
                details = {"step": node}
                if node in {"prune_before_model", "prune_after_turn"}:
                    details["messages_before"] = len(data.get("input", {}).get("messages", []))
                self._start_step(run_id, details)
        elif event_type == "on_chain_end":
            if name == "LangGraph":
                self._result = data.get("output")
            else:
                step = self._finish_step(run_id)
                if step and step["step"] in {"prune_before_model", "prune_after_turn"}:
                    removed = data.get("output", {}).get("messages", [])
                    removed_count = sum(isinstance(message, RemoveMessage) for message in removed)
                    step["messages_removed"] = removed_count
                    step["messages_retained"] = step["messages_before"] - removed_count
        elif event_type == "on_chain_error":
            self._fail_step(run_id, data.get("error"))
        elif event_type == "on_tool_start":
            self._start_step(
                run_id,
                {
                    "step": "tool",
                    "tool_name": name,
                    "arguments": data.get("input", {}),
                },
            )
        elif event_type == "on_tool_end":
            output = data.get("output")
            if isinstance(output, ToolMessage) and output.status == "error":
                self._fail_step(run_id, output.content)
            else:
                step = self._finish_step(run_id)
                if step is not None:
                    step["result"] = _trace_tool_output(output)
        elif event_type == "on_tool_error":
            self._fail_step(run_id, data.get("error"))

    def result(self) -> dict[str, Any]:
        if self._result is None:
            raise RuntimeError("Agent graph ended without returning a state")
        return self._result

    def complete(self, result: dict[str, Any]) -> None:
        messages = result.get("messages", [])
        if messages:
            self.record["final_answer"] = messages[-1].content
        self.record["status"] = "completed"

    def fail(self, error: Exception) -> None:
        self.record["status"] = "failed"
        self.record["error"] = _error_details(error)

    def write(self) -> None:
        self.record["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.record["duration_ms"] = round((time.perf_counter() - self._started) * 1000, 3)
        append_trace_record(self.record)

    def _start_step(self, run_id: str, details: dict[str, Any]) -> None:
        step = {"status": "running", **details}
        self.record["steps"].append(step)
        self._steps[run_id] = step
        self._step_starts[run_id] = time.perf_counter()

    def _finish_step(self, run_id: str) -> dict[str, Any] | None:
        step = self._steps.get(run_id)
        if step is None:
            return None
        step["status"] = "completed"
        step["duration_ms"] = round((time.perf_counter() - self._step_starts[run_id]) * 1000, 3)
        return step

    def _fail_step(self, run_id: str, error: Any) -> None:
        step = self._steps.get(run_id)
        if step is None:
            return
        step["status"] = "error"
        step["duration_ms"] = round((time.perf_counter() - self._step_starts[run_id]) * 1000, 3)
        step["error"] = _error_details(error)


def _error_details(error: Any) -> dict[str, str]:
    if isinstance(error, BaseException):
        return {"type": type(error).__name__, "message": str(error)}
    if isinstance(error, list):
        messages = [
            item["text"]
            for item in error
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        if messages:
            return {"type": "ToolError", "message": "\n".join(messages)}
    return {"type": "ToolError", "message": str(error)}


def _trace_tool_output(output: Any) -> str:
    if isinstance(output, ToolMessage):
        output = output.content
    content = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, default=str)
    if len(content) > MAX_TRACE_TOOL_OUTPUT_CHARS:
        content = (
            content[: MAX_TRACE_TOOL_OUTPUT_CHARS - len(TRACE_TRUNCATION_MARKER)]
            + TRACE_TRUNCATION_MARKER
        )
    return content


def append_trace_record(record: dict[str, Any]) -> None:
    path = Path(TRACE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as trace_file:
        trace_file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
