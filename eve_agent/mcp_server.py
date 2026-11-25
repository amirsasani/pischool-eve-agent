from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from eve_agent.api_clients import (
    get_historical_weather as fetch_historical_weather,
    search_open_wildfires,
)
from eve_agent.settings import MCP_SERVER_HOST, MCP_SERVER_PORT

mcp = FastMCP(
    "EVE Earth Observation",
    instructions=(
        "Report data returned by NASA EONET and Open-Meteo. "
        "EONET wildfire-category events may include prescribed burns."
    ),
    host=MCP_SERVER_HOST,
    port=MCP_SERVER_PORT,
)


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
