from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from eve_agent.api_clients import (
    geocode_location,
    get_historical_weather as fetch_historical_weather,
    search_open_wildfires,
    validate_wildfire_radius_km,
    wildfire_bbox_for_radius,
)
from eve_agent.settings import MCP_SERVER_HOST, MCP_SERVER_PORT

mcp = FastMCP(
    "EVE Earth Observation",
    instructions=(
        "Use Open-Meteo Geocoding to resolve city names; do not invent coordinates. "
        "Ask the user to disambiguate multiple location matches. "
        "Location-based wildfire searches require an explicit radius in kilometers. "
        "EONET wildfire-category events may include prescribed burns."
    ),
    host=MCP_SERVER_HOST,
    port=MCP_SERVER_PORT,
)


def _resolve_location_matches(
    city: str,
    country: str | None,
    matches: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    if not matches:
        return "not_found", []

    terms = [term.strip().casefold() for term in city.split(",") if term.strip()]
    if country:
        terms.append(country.strip().casefold())
    city_name = terms[0] if terms else city.strip().casefold()
    candidates = [
        match for match in matches
        if isinstance(match.get("name"), str)
        and match["name"].strip().casefold() == city_name
    ]
    if not candidates:
        return "ambiguous", matches

    for qualifier in terms[1:]:
        qualified = [
            match
            for match in candidates
            if any(
                isinstance(match.get(field), str)
                and match[field].strip().casefold() == qualifier
                for field in ("admin1", "admin2", "country", "country_code")
            )
        ]
        if qualified:
            candidates = qualified

    if len(candidates) == 1:
        return "resolved", candidates

    regions = {
        (match.get("country"), match.get("admin1"), match.get("admin2"))
        for match in candidates
    }
    populations = [match.get("population") for match in candidates]
    if len(regions) == 1 and all(isinstance(value, int) for value in populations):
        largest = max(populations)
        most_populous = [
            match for match in candidates if match["population"] == largest
        ]
        if len(most_populous) == 1:
            return "resolved", most_populous
    return "ambiguous", candidates


@mcp.tool()
def resolve_location(city: str, country: str | None = None) -> dict[str, Any]:
    """Resolve a city name to candidate coordinates using Open-Meteo Geocoding.

    If several matches are returned, ask the user to specify the country or
    administrative region before using coordinates.
    """
    status, matches = _resolve_location_matches(
        city,
        country,
        geocode_location(city, country),
    )
    return {
        "source": "Open-Meteo Geocoding API",
        "query": {"city": city, "country": country},
        "status": status,
        "matches": matches,
    }


@mcp.tool()
def search_wildfire_events(
    min_lon: float,
    max_lat: float,
    max_lon: float,
    min_lat: float,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Find open EONET wildfire-category events inside a bounding box.

    The bounding box is ordered as minimum longitude, maximum latitude,
    maximum longitude, minimum latitude. Supply start_date and end_date
    together in YYYY-MM-DD format, or omit both.
    """
    events = search_open_wildfires(
        (min_lon, max_lat, max_lon, min_lat),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return {
        "source": "NASA EONET",
        "bbox": [min_lon, max_lat, max_lon, min_lat],
        "events": [_summarize_event(event) for event in events],
    }


@mcp.tool()
def search_wildfires_near_location(
    city: str,
    radius_km: float,
    country: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Find open EONET wildfires within an explicit radius of a resolved city.

    The radius is required in kilometers. If the city is ambiguous, returns
    candidate locations without running a wildfire search.
    """
    validate_wildfire_radius_km(radius_km)
    status, matches = _resolve_location_matches(
        city,
        country,
        geocode_location(city, country),
    )
    if status != "resolved":
        return {
            "source": "Open-Meteo Geocoding API",
            "status": status,
            "matches": matches,
            "events": [],
        }

    location = matches[0]
    bbox = wildfire_bbox_for_radius(
        location["latitude"],
        location["longitude"],
        radius_km,
    )
    events = search_open_wildfires(
        bbox,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return {
        "source": "NASA EONET",
        "location": location,
        "radius_km": radius_km,
        "bbox": list(bbox),
        "events": [_summarize_event(event) for event in events],
    }


@mcp.tool()
def get_historical_weather(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Get daily maximum temperature and precipitation for a location.

    Dates must use YYYY-MM-DD format. The response includes timezone and units
    from Open-Meteo.
    """
    result = fetch_historical_weather(latitude, longitude, start_date, end_date)
    return {
        "source": "Open-Meteo Historical Weather API",
        "requested_location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "resolved_location": {
            "latitude": result.get("latitude"),
            "longitude": result.get("longitude"),
            "timezone": result.get("timezone"),
            "elevation": result.get("elevation"),
        },
        "daily_units": result.get("daily_units"),
        "daily": result.get("daily"),
    }


def _summarize_event(event: dict[str, Any]) -> dict[str, Any]:
    geometries = []
    for geometry in event.get("geometry", []):
        item = {
            key: geometry[key]
            for key in (
                "date",
                "type",
                "magnitudeValue",
                "magnitudeUnit",
                "magnitudeDescription",
            )
            if key in geometry
        }
        if geometry.get("type") == "Point" and "coordinates" in geometry:
            item["coordinates"] = geometry["coordinates"]
        geometries.append(item)

    return {
        key: event[key]
        for key in ("id", "title", "description", "link", "closed", "categories", "sources")
        if key in event
    } | {"geometry": geometries}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
