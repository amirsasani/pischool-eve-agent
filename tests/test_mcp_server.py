from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from mcp.shared.memory import create_connected_server_and_client_session

from eve_agent.api_clients import ExternalAPIError
from eve_agent.mcp_server import mcp


class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_exposes_both_api_tools(self) -> None:
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            result = await client.list_tools()

        self.assertEqual(
            {tool.name for tool in result.tools},
            {"search_wildfire_events", "get_historical_weather"},
        )

    async def test_wildfire_tool_calls_api_client_and_returns_compact_data(self) -> None:
        event = {
            "id": "EONET_1",
            "title": "Example wildfire",
            "geometry": [
                {
                    "date": "2026-11-24T00:00:00Z",
                    "type": "Point",
                    "coordinates": [-79.5, 38.5],
                }
            ],
        }
        with patch("eve_agent.mcp_server.search_open_wildfires", return_value=[event]) as api:
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as client:
                result = await client.call_tool(
                    "search_wildfire_events",
                    {
                        "min_lon": -80,
                        "max_lat": 39,
                        "max_lon": -79,
                        "min_lat": 38,
                        "limit": 5,
                    },
                )

        api.assert_called_once_with(
            (-80, 39, -79, 38),
            start_date=None,
            end_date=None,
            limit=5,
        )
        self.assertFalse(result.isError)
        payload = json.loads(result.content[0].text)
        self.assertEqual(payload["events"][0]["id"], "EONET_1")
        self.assertEqual(
            payload["events"][0]["geometry"][0]["coordinates"],
            [-79.5, 38.5],
        )

    async def test_weather_tool_returns_daily_data(self) -> None:
        weather = {
            "latitude": 34.05,
            "longitude": -118.24,
            "timezone": "America/Los_Angeles",
            "elevation": 87,
            "daily_units": {"temperature_2m_max": "°C"},
            "daily": {"time": ["2024-08-01"], "temperature_2m_max": [30.9]},
        }
        with patch(
            "eve_agent.mcp_server.fetch_historical_weather",
            return_value=weather,
        ) as api:
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as client:
                result = await client.call_tool(
                    "get_historical_weather",
                    {
                        "latitude": 34.05,
                        "longitude": -118.24,
                        "start_date": "2024-08-01",
                        "end_date": "2024-08-01",
                    },
                )

        api.assert_called_once_with(34.05, -118.24, "2024-08-01", "2024-08-01")
        self.assertFalse(result.isError)
        payload = json.loads(result.content[0].text)
        self.assertEqual(payload["daily"], weather["daily"])
        self.assertEqual(
            payload["resolved_location"]["timezone"],
            "America/Los_Angeles",
        )

    async def test_weather_tool_returns_upstream_error_as_mcp_tool_error(self) -> None:
        with patch(
            "eve_agent.mcp_server.fetch_historical_weather",
            side_effect=ExternalAPIError("Open-Meteo", "HTTP 400: Invalid date format"),
        ):
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as client:
                result = await client.call_tool(
                    "get_historical_weather",
                    {
                        "latitude": 34.05,
                        "longitude": -118.24,
                        "start_date": "2024-08-01",
                        "end_date": "2024-08-03",
                    },
                )

        self.assertTrue(result.isError)
        self.assertIn("Invalid date format", result.content[0].text)


if __name__ == "__main__":
    unittest.main()
