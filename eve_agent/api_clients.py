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
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
DEFAULT_TIMEOUT_SECONDS = 10
MAX_WILDFIRE_EVENTS = 100
MAX_LOCATION_RESULTS = 10
MAX_WILDFIRE_RADIUS_KM = 500


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


def geocode_location(
    city: str,
    country: str | None = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Return Open-Meteo location matches for a city and optional country."""
    if not isinstance(city, str) or not city.strip():
        raise ValueError("city must not be empty")
    if country is not None and (not isinstance(country, str) or not country.strip()):
        raise ValueError("country must not be empty when provided")

    query = city.strip()
    if country is not None:
        query = f"{query}, {country.strip()}"
    payload = _fetch_json(
        "Open-Meteo Geocoding",
        OPEN_METEO_GEOCODING_URL,
        {"name": query, "count": str(MAX_LOCATION_RESULTS), "language": "en", "format": "json"},
        timeout,
    )
    results = payload.get("results", [])
    if results is None:
        return []
    if not isinstance(results, list):
        raise ExternalAPIError("Open-Meteo Geocoding", "returned an unexpected results list")

    locations = []
    for result in results:
        if not isinstance(result, dict):
            raise ExternalAPIError("Open-Meteo Geocoding", "returned an invalid location")
        name = result.get("name")
        latitude = result.get("latitude")
        longitude = result.get("longitude")
        if not isinstance(name, str):
            raise ExternalAPIError("Open-Meteo Geocoding", "returned a location without a name")
        try:
            _validate_coordinate(latitude, "latitude", -90, 90)
            _validate_coordinate(longitude, "longitude", -180, 180)
        except ValueError as exc:
            raise ExternalAPIError("Open-Meteo Geocoding", str(exc)) from exc

        location = {
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
        }
        for key in (
            "id",
            "admin1",
            "admin2",
            "country",
            "country_code",
            "feature_code",
            "timezone",
            "population",
        ):
            if isinstance(result.get(key), str):
                location[key] = result[key]
            elif key in {"id", "population"} and isinstance(result.get(key), int):
                location[key] = result[key]
        locations.append(location)
    return locations


def validate_wildfire_radius_km(radius_km: float) -> None:
    if (
        isinstance(radius_km, bool)
        or not isinstance(radius_km, (int, float))
        or not math.isfinite(radius_km)
        or not 0 < radius_km <= MAX_WILDFIRE_RADIUS_KM
    ):
        raise ValueError(f"radius_km must be greater than 0 and at most {MAX_WILDFIRE_RADIUS_KM}")


def wildfire_bbox_for_radius(
    latitude: float,
    longitude: float,
    radius_km: float,
) -> tuple[float, float, float, float]:
    """Calculate an EONET-ordered bounding box around a point and radius."""
    _validate_coordinate(latitude, "latitude", -90, 90)
    _validate_coordinate(longitude, "longitude", -180, 180)
    validate_wildfire_radius_km(radius_km)

    # shortcut: local spherical approximation; use geodesic bounds if larger radii are allowed.
    latitude_delta = radius_km / 111.32
    min_lat = max(-90, latitude - latitude_delta)
    max_lat = min(90, latitude + latitude_delta)

    if min_lat <= -90 or max_lat >= 90:
        min_lon, max_lon = -180, 180
    else:
        cosine = math.cos(math.radians(latitude))
        longitude_delta = radius_km / (111.32 * cosine)
        min_lon = longitude - longitude_delta
        max_lon = longitude + longitude_delta
        if min_lon < -180 or max_lon > 180:
            raise ValueError(
                "radius crosses the antimeridian; use a different location or smaller radius"
            )

    return min_lon, max_lat, max_lon, min_lat


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
