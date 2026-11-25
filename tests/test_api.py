import unittest
from unittest.mock import AsyncMock, call, patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from eve_agent.api import app


class AgentAPITests(unittest.TestCase):
    def test_chat_forwards_session_and_message_to_agent(self) -> None:
        fake_agent = object()
        with (
            patch("eve_agent.api.build_agent", new_callable=AsyncMock) as build_agent,
            patch(
                "eve_agent.api.invoke_agent_turn",
                new_callable=AsyncMock,
            ) as invoke_agent_turn,
        ):
            build_agent.return_value = fake_agent
            invoke_agent_turn.return_value = {
                "messages": [AIMessage(content="Open-Meteo says 30.9 °C")]
            }

            with TestClient(app) as client:
                first_response = client.post(
                    "/chat",
                    json={
                        "session_id": "weather-session",
                        "message": "What was the temperature?",
                    },
                )
                second_response = client.post(
                    "/chat",
                    json={
                        "session_id": "weather-session",
                        "message": "And the precipitation?",
                    },
                )
                invalid_response = client.post(
                    "/chat",
                    json={"session_id": "  ", "message": "hello"},
                )

        self.assertEqual(
            first_response.json(),
            {"session_id": "weather-session", "answer": "Open-Meteo says 30.9 °C"},
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(invalid_response.status_code, 422)
        build_agent.assert_awaited_once_with()
        self.assertEqual(
            invoke_agent_turn.await_args_list,
            [
                call(fake_agent, "weather-session", "What was the temperature?"),
                call(fake_agent, "weather-session", "And the precipitation?"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
