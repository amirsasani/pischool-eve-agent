import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool

from eve_agent.agent import (
    MAX_HISTORY_TURNS,
    MAX_TOOL_OUTPUT_CHARS,
    TOOL_OUTPUT_TRUNCATION_MARKER,
    SYSTEM_PROMPT,
    _create_agent_graph,
    invoke_agent_turn,
)
from eve_agent.tracing import AgentTrace


class AgentGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_calls_tool_then_answers_from_its_result(self) -> None:
        tool_calls: list[dict[str, object]] = []

        @tool
        def get_historical_weather(
            latitude: float,
            longitude: float,
            start_date: str,
            end_date: str,
        ) -> str:
            """Return example historical weather data."""
            tool_calls.append(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
            return "Open-Meteo maximum temperature: 30.9 °C"

        model_inputs: list[list[object]] = []

        def scripted_model(messages: list[object]) -> AIMessage:
            model_inputs.append(messages)
            tool_result = next(
                (message for message in reversed(messages) if isinstance(message, ToolMessage)),
                None,
            )
            if tool_result is not None:
                return AIMessage(content=f"According to Open-Meteo: {tool_result.content}")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_historical_weather",
                        "args": {
                            "latitude": 34.05,
                            "longitude": -118.24,
                            "start_date": "2024-08-01",
                            "end_date": "2024-08-03",
                        },
                        "id": "weather-call",
                        "type": "tool_call",
                    }
                ],
            )

        agent = _create_agent_graph(RunnableLambda(scripted_model), [get_historical_weather])
        result = await invoke_agent_turn(
            agent,
            "weather-session",
            "What was the weather in Los Angeles?",
        )

        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["start_date"], "2024-08-01")
        self.assertIn("30.9 °C", result["messages"][-1].content)
        self.assertEqual(len(model_inputs), 2)
        self.assertTrue(
            all(
                isinstance(messages[0], SystemMessage)
                and messages[0].content == SYSTEM_PROMPT
                for messages in model_inputs
            )
        )

    async def test_history_is_persisted_per_session_id(self) -> None:
        model_inputs: list[list[object]] = []

        def scripted_model(messages: list[object]) -> AIMessage:
            model_inputs.append(messages)
            return AIMessage(content="Understood.")

        agent = _create_agent_graph(RunnableLambda(scripted_model), [])

        await invoke_agent_turn(agent, "session-a", "The site is 34.05, -118.24.")
        await invoke_agent_turn(agent, "session-a", "What was the same date?")
        await invoke_agent_turn(agent, "session-b", "Start a new conversation.")

        human_messages = [
            [message.content for message in messages if isinstance(message, HumanMessage)]
            for messages in model_inputs
        ]
        self.assertEqual(
            human_messages,
            [
                ["The site is 34.05, -118.24."],
                ["The site is 34.05, -118.24.", "What was the same date?"],
                ["Start a new conversation."],
            ],
        )

    async def test_empty_session_id_is_rejected(self) -> None:
        agent = _create_agent_graph(RunnableLambda(lambda _: AIMessage(content="ok")), [])

        with self.assertRaisesRegex(ValueError, "session_id"):
            await invoke_agent_turn(agent, "  ", "hello")

    async def test_history_is_limited_to_latest_user_turns(self) -> None:
        model_inputs: list[list[object]] = []

        def scripted_model(messages: list[object]) -> AIMessage:
            model_inputs.append(messages)
            return AIMessage(content="Understood.")

        agent = _create_agent_graph(RunnableLambda(scripted_model), [])
        for turn in range(MAX_HISTORY_TURNS + 2):
            await invoke_agent_turn(agent, "long-session", f"Turn {turn}")

        latest_human_messages = [
            message.content
            for message in model_inputs[-1]
            if isinstance(message, HumanMessage)
        ]
        self.assertEqual(
            latest_human_messages,
            [f"Turn {turn}" for turn in range(2, MAX_HISTORY_TURNS + 2)],
        )

        snapshot = agent.get_state({"configurable": {"thread_id": "long-session"}})
        retained_human_messages = [
            message.content
            for message in snapshot.values["messages"]
            if isinstance(message, HumanMessage)
        ]
        self.assertEqual(retained_human_messages, latest_human_messages)

    async def test_oversized_tool_output_is_truncated_before_model_call(self) -> None:
        observed_tool_results: list[ToolMessage] = []

        @tool
        def get_large_result() -> str:
            """Return a large example result."""
            return "x" * (MAX_TOOL_OUTPUT_CHARS + 500)

        def scripted_model(messages: list[object]) -> AIMessage:
            tool_result = next(
                (message for message in reversed(messages) if isinstance(message, ToolMessage)),
                None,
            )
            if tool_result is not None:
                observed_tool_results.append(tool_result)
                return AIMessage(content="Done.")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_large_result",
                        "args": {},
                        "id": "large-result-call",
                        "type": "tool_call",
                    }
                ],
            )

        agent = _create_agent_graph(RunnableLambda(scripted_model), [get_large_result])
        result = await invoke_agent_turn(agent, "large-tool-session", "Get the result.")
        stored_tool_result = next(
            message for message in result["messages"] if isinstance(message, ToolMessage)
        )

        self.assertTrue(observed_tool_results)
        self.assertLessEqual(len(observed_tool_results[0].content), MAX_TOOL_OUTPUT_CHARS)
        self.assertTrue(observed_tool_results[0].content.endswith(TOOL_OUTPUT_TRUNCATION_MARKER))
        self.assertLessEqual(len(stored_tool_result.content), MAX_TOOL_OUTPUT_CHARS)

    async def test_trace_records_tool_call_and_final_answer(self) -> None:
        @tool
        def lookup_weather(latitude: float, date: str) -> str:
            """Return example weather data."""
            return f"Maximum temperature at {latitude} on {date}: 30.9 °C"

        def scripted_model(messages: list[object]) -> AIMessage:
            tool_result = next(
                (message for message in reversed(messages) if isinstance(message, ToolMessage)),
                None,
            )
            if tool_result is not None:
                return AIMessage(content=f"According to Open-Meteo: {tool_result.content}")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "lookup_weather",
                        "args": {"latitude": 34.05, "date": "2024-08-01"},
                        "id": "trace-weather-call",
                        "type": "tool_call",
                    }
                ],
            )

        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "agent-traces.jsonl"
            with patch("eve_agent.tracing.TRACE_FILE", trace_path):
                agent = _create_agent_graph(
                    RunnableLambda(scripted_model),
                    [lookup_weather],
                )
                result = await invoke_agent_turn(
                    agent,
                    "trace-session",
                    "What was the temperature at 34.05 on 2024-08-01?",
                )

            trace = json.loads(trace_path.read_text(encoding="utf-8").strip())

        tool_step = next(step for step in trace["steps"] if step["step"] == "tool")
        self.assertEqual(trace["session_id"], "trace-session")
        self.assertEqual(trace["status"], "completed")
        self.assertIn("30.9 °C", trace["final_answer"])
        self.assertEqual(tool_step["tool_name"], "lookup_weather")
        self.assertEqual(tool_step["arguments"], {"latitude": 34.05, "date": "2024-08-01"})
        self.assertGreaterEqual(tool_step["duration_ms"], 0)
        self.assertIn("assistant", [step["step"] for step in trace["steps"]])
        self.assertIn("30.9 °C", result["messages"][-1].content)

    async def test_tool_error_is_traced_and_agent_returns_failure_message(self) -> None:
        @tool
        def failing_tool() -> str:
            """Simulate an upstream service failure."""
            raise RuntimeError("upstream unavailable")

        def scripted_model(messages: list[object]) -> AIMessage:
            tool_result = next(
                (message for message in reversed(messages) if isinstance(message, ToolMessage)),
                None,
            )
            if tool_result is not None:
                return AIMessage(content=f"The attempted lookup failed: {tool_result.content}")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "failing_tool",
                        "args": {},
                        "id": "trace-error-call",
                        "type": "tool_call",
                    }
                ],
            )

        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "agent-traces.jsonl"
            with patch("eve_agent.tracing.TRACE_FILE", trace_path):
                agent = _create_agent_graph(RunnableLambda(scripted_model), [failing_tool])
                result = await invoke_agent_turn(agent, "error-session", "Try the lookup.")

            trace = json.loads(trace_path.read_text(encoding="utf-8").strip())

        tool_step = next(step for step in trace["steps"] if step["step"] == "tool")
        self.assertEqual(trace["status"], "completed")
        self.assertEqual(tool_step["status"], "error")
        self.assertEqual(tool_step["tool_name"], "failing_tool")
        self.assertEqual(tool_step["error"]["type"], "RuntimeError")
        self.assertIn("upstream unavailable", tool_step["error"]["message"])
        self.assertIn("failed", result["messages"][-1].content)

    def test_mcp_tool_error_trace_extracts_readable_message(self) -> None:
        trace = AgentTrace("error-session", "Try the lookup.")
        trace.observe(
            {
                "event": "on_tool_start",
                "name": "get_historical_weather",
                "run_id": "tool-run",
                "data": {"input": {"start_date": "2024-99-99"}},
            }
        )
        trace.observe(
            {
                "event": "on_tool_end",
                "name": "get_historical_weather",
                "run_id": "tool-run",
                "data": {
                    "output": ToolMessage(
                        content=[
                            {
                                "type": "text",
                                "text": "Error executing tool: start_date must use YYYY-MM-DD format",
                            }
                        ],
                        name="get_historical_weather",
                        tool_call_id="failed-call",
                        status="error",
                    )
                },
            }
        )

        tool_step = trace.record["steps"][0]
        self.assertEqual(tool_step["status"], "error")
        self.assertEqual(
            tool_step["error"]["message"],
            "Error executing tool: start_date must use YYYY-MM-DD format",
        )


if __name__ == "__main__":
    unittest.main()
