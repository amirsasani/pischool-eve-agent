# EVE Earth Observation API Clients

This repository contains the API-client portion of a Pi School AI Research
Engineer interview assignment. It provides Python clients for NASA EONET
wildfire events and Open-Meteo historical weather.

## API clients

[`eve_agent/api_clients.py`](eve_agent/api_clients.py) provides:

- `search_open_wildfires(bbox, ...)` to retrieve open EONET wildfire-category
  events within a bounding box. The box format is
  `(min_lon, max_lat, max_lon, min_lat)`. Optional start and end dates and a
  result limit are supported.
- `get_historical_weather(latitude, longitude, start_date, end_date)` to
  retrieve daily maximum temperature and total precipitation.

Inputs are validated before requests are made. Upstream request failures or
unexpected responses raise `ExternalAPIError`.

EONET events are catalogued wildfire-category events and may include prescribed
burns; the category alone does not establish that a fire is uncontrolled.

## Data sources

- [NASA EONET API v3](https://eonet.gsfc.nasa.gov/docs/v3)
- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)

The endpoints used here do not require an API key for the demonstrated
requests.

## Requirements

- Python 3.10 or newer
- Network access to the APIs for live requests

The clients and tests use only the Python standard library.

## Run tests

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

Tests use mocked HTTP responses and do not require network access.

## Example

```python
from eve_agent.api_clients import get_historical_weather, search_open_wildfires

events = search_open_wildfires((-80, 39, -79, 38), limit=5)
weather = get_historical_weather(
    34.05, -118.24, "2024-08-01", "2024-08-03"
)

print(events)
print(weather)
```
