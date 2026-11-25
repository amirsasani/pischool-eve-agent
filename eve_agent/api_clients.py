"""Small synchronous clients for the external APIs used by the agent."""

from __future__ import annotations

import json
import math
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

EONET_EVENTS_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DEFAULT_TIMEOUT_SECONDS = 10
MAX_WILDFIRE_EVENTS = 100


class ExternalAPIError(RuntimeError):
    """An external API request failed or returned an unusable response."""

    def __init__(
        self,
        service: str,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        self.service = service
        self.status_code = status_code
        super().__init__(f"{service} API: {message}")


def _error_detail(body: bytes) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return "returned a non-JSON error response"

    if isinstance(payload, dict):
        for key in ("reason", "message"):
            detail = payload.get(key)
            if isinstance(detail, str) and detail:
                return detail
    return "returned an error response"


def _fetch_json(
    service: str,
    base_url: str,
    params: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    request = Request(
        f"{base_url}?{urlencode(params)}",
        headers={
            "Accept": "application/json",
            "User-Agent": "eve-agent/0.1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
    except HTTPError as exc:
        try:
            detail = _error_detail(exc.read())
        finally:
            exc.close()
        raise ExternalAPIError(
            service,
            f"HTTP {exc.code}: {detail}",
            status_code=exc.code,
        ) from exc
    except URLError as exc:
        raise ExternalAPIError(service, f"request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ExternalAPIError(service, "request timed out") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ExternalAPIError(service, "returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ExternalAPIError(service, "returned an unexpected response")
    if payload.get("error") is True:
        detail = payload.get("reason")
        message = detail if isinstance(detail, str) else "reported an error"
        raise ExternalAPIError(service, message)
    return payload


def _validate_date(value: str, name: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD format") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{name} must use YYYY-MM-DD format")
    return parsed


def _validate_date_range(start_date: str, end_date: str) -> None:
    if _validate_date(start_date, "start_date") > _validate_date(
        end_date, "end_date"
    ):
        raise ValueError("start_date must be on or before end_date")


def _validate_coordinate(value: float, name: str, lower: float, upper: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not lower <= value <= upper
    ):
        raise ValueError(f"{name} must be between {lower} and {upper}")


def search_open_wildfires(
    bbox: tuple[float, float, float, float],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Return open EONET wildfire events in a bounding box.

    The bounding box is ordered as (minimum longitude, maximum latitude,
    maximum longitude, minimum latitude), matching EONET's API.
    """
    if len(bbox) != 4:
        raise ValueError("bbox must contain min_lon, max_lat, max_lon, min_lat")
    min_lon, max_lat, max_lon, min_lat = bbox
    _validate_coordinate(min_lon, "min_lon", -180, 180)
    _validate_coordinate(max_lon, "max_lon", -180, 180)
    _validate_coordinate(min_lat, "min_lat", -90, 90)
    _validate_coordinate(max_lat, "max_lat", -90, 90)
    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError("bbox minimum coordinates must be less than maximum coordinates")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_WILDFIRE_EVENTS
    ):
        raise ValueError(f"limit must be between 1 and {MAX_WILDFIRE_EVENTS}")
    if (start_date is None) != (end_date is None):
        raise ValueError("start_date and end_date must be provided together")

    params = {
        "category": "wildfires",
        "status": "open",
        "limit": str(limit),
        "bbox": ",".join(str(coordinate) for coordinate in bbox),
    }
    if start_date is not None and end_date is not None:
        _validate_date_range(start_date, end_date)
        params["start"] = start_date
        params["end"] = end_date

    payload = _fetch_json("EONET", EONET_EVENTS_URL, params, timeout)
    events = payload.get("events")
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ExternalAPIError("EONET", "returned an unexpected events list")
    return events


def get_historical_weather(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Return daily maximum temperature and precipitation from Open-Meteo."""
    _validate_coordinate(latitude, "latitude", -90, 90)
    _validate_coordinate(longitude, "longitude", -180, 180)
    _validate_date_range(start_date, end_date)

    params = {
        "latitude": str(latitude),
        "longitude": str(longitude),
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max,precipitation_sum",
        "timezone": "auto",
    }
    return _fetch_json("Open-Meteo", OPEN_METEO_ARCHIVE_URL, params, timeout)
