from __future__ import annotations

import json
import unittest
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock, patch

from eve_agent.api_clients import (
    ExternalAPIError,
    geocode_location,
    get_historical_weather,
    search_open_wildfires,
    wildfire_bbox_for_radius,
)


class FakeResponse:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.body = json.dumps(payload).encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class ApiClientTests(unittest.TestCase):
    @patch("eve_agent.api_clients.urlopen")
    def test_geocoding_returns_candidate_coordinates(
        self, mock_urlopen: MagicMock
    ) -> None:
        mock_urlopen.return_value = FakeResponse(
            {
                "results": [
                    {
                        "name": "Turin",
                        "latitude": 45.0703,
                        "longitude": 7.6869,
                        "admin1": "Piedmont",
                        "country": "Italy",
                    }
                ]
            }
        )

        locations = geocode_location("Turin", "Italy")

        params = parse_qs(urlparse(mock_urlopen.call_args.args[0].full_url).query)
        self.assertEqual(params["name"], ["Turin, Italy"])
        self.assertEqual(locations[0]["latitude"], 45.0703)
        self.assertEqual(locations[0]["country"], "Italy")

    def test_radius_creates_eonet_ordered_bounding_box(self) -> None:
        bbox = wildfire_bbox_for_radius(0, 0, 10)

        self.assertAlmostEqual(bbox[0], -10 / 111.32)
        self.assertAlmostEqual(bbox[1], 10 / 111.32)
        self.assertAlmostEqual(bbox[2], 10 / 111.32)
        self.assertAlmostEqual(bbox[3], -10 / 111.32)

    def test_radius_must_be_positive_and_limited(self) -> None:
        with self.assertRaisesRegex(ValueError, "radius_km"):
            wildfire_bbox_for_radius(0, 0, 0)
        with self.assertRaisesRegex(ValueError, "radius_km"):
            wildfire_bbox_for_radius(0, 0, 501)

    @patch("eve_agent.api_clients.urlopen")
    def test_search_wildfires_sends_bounded_eonet_query(
        self, mock_urlopen: MagicMock
    ) -> None:
        mock_urlopen.return_value = FakeResponse({"events": [{"id": "EONET_1"}]})

        result = search_open_wildfires(
            (-80, 39, -79, 38),
            start_date="2026-11-01",
            end_date="2026-11-24",
            limit=5,
        )

        request = mock_urlopen.call_args.args[0]
        params = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(params["bbox"], ["-80,39,-79,38"])
        self.assertEqual(params["category"], ["wildfires"])
        self.assertEqual(params["limit"], ["5"])
        self.assertEqual(result, [{"id": "EONET_1"}])

    @patch("eve_agent.api_clients.urlopen")
    def test_weather_requests_daily_data(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = FakeResponse({"daily": {"time": ["2024-08-01"]}})

        result = get_historical_weather(
            34.05,
            -118.24,
            "2024-08-01",
            "2024-08-03",
        )

        request = mock_urlopen.call_args.args[0]
        params = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(
            params["daily"],
            ["temperature_2m_max,precipitation_sum"],
        )
        self.assertEqual(params["timezone"], ["auto"])
        self.assertIn("daily", result)

    @patch("eve_agent.api_clients.urlopen")
    def test_invalid_date_is_reported_as_external_api_error(
        self, mock_urlopen: MagicMock
    ) -> None:
        mock_urlopen.side_effect = HTTPError(
            "https://example.test",
            400,
            "Bad Request",
            hdrs=None,
            fp=BytesIO(b'{"error":true,"reason":"Invalid date format"}'),
        )

        with self.assertRaisesRegex(ExternalAPIError, "Invalid date format"):
            get_historical_weather(
                34.05,
                -118.24,
                "2024-08-01",
                "2024-08-03",
            )

    @patch("eve_agent.api_clients.urlopen")
    def test_invalid_input_fails_before_network_request(
        self, mock_urlopen: MagicMock
    ) -> None:
        with self.assertRaisesRegex(ValueError, "start_date"):
            get_historical_weather(34.05, -118.24, "not-a-date", "2024-08-03")
        mock_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
