import unittest

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


if __name__ == "__main__":
    unittest.main()
