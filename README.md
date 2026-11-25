# EVE Earth Observation MCP Server

This repository contains API clients and an MCP server for NASA EONET
wildfire-category events and Open-Meteo historical weather. It is part of a
Pi School AI Research Engineer interview assignment.

## MCP server

[`eve_agent/mcp_server.py`](eve_agent/mcp_server.py) exposes two MCP tools over
Streamable HTTP at `http://127.0.0.1:8001/mcp`:

- `search_wildfire_events` retrieves open EONET wildfire-category events
  inside a bounding box. The box arguments are minimum longitude, maximum
  latitude, maximum longitude, and minimum latitude. Optional start and end
  dates must be supplied together; `limit` defaults to 20.
- `get_historical_weather` retrieves daily maximum temperature and total
  precipitation for the requested coordinates and dates.

The EONET tool keeps event identifiers, titles, descriptions, source links,
magnitudes, and geometry dates. Point coordinates are included; polygon
coordinates are omitted to keep the tool response compact.

Both tools call the API clients in
[`eve_agent/api_clients.py`](eve_agent/api_clients.py). Inputs are validated
before requests are made; upstream failures are returned as MCP tool errors.

EONET events are catalogued wildfire-category events and may include prescribed
burns, so the category alone does not establish that a fire is uncontrolled.

## Data sources

- [NASA EONET API v3](https://eonet.gsfc.nasa.gov/docs/v3)
- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)

The endpoints used here do not require an API key for the demonstrated
requests.

## Requirements

- Python 3.10 or newer
- Network access to the APIs for live requests
- Dependencies pinned in [`requirements.txt`](requirements.txt)

## Install and run

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
python -m eve_agent.mcp_server
```

The `.env` file sets `MCP_SERVER_HOST` and `MCP_SERVER_PORT`; defaults are
`127.0.0.1` and `8001`. The MCP client uses these same settings to connect at
`http://<host>:<port>/mcp`. `.env` is ignored by Git; commit only the
non-sensitive `.env.example` template.

## Load tools through MCP

With the MCP server running, the LangChain MCP adapter can discover its tools:

```python
import asyncio

from eve_agent.mcp_client import load_mcp_tools

tools = asyncio.run(load_mcp_tools())
print([tool.name for tool in tools])
```

The tools are loaded over Streamable HTTP by
[`eve_agent/mcp_client.py`](eve_agent/mcp_client.py).

## Run tests

From the repository root, with the requirements installed:

```bash
python3 -m unittest discover -s tests -v
```

API client and MCP server tests use mocked responses and do not require network
access.
