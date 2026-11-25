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
- Ollama installed and running
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
`127.0.0.1` and `8001`. `OLLAMA_MODEL` selects the local model and defaults to
`qwen3.5:4b`. The MCP client uses the server settings to connect at
`http://<host>:<port>/mcp`. `.env` is ignored by Git; commit only the
non-sensitive `.env.example` template.

## Run the agent

Pull the configured model if it is not already installed:

```bash
ollama pull qwen3.5:4b
```

Start the MCP server in one terminal:

```bash
python -m eve_agent.mcp_server
```

In another terminal, invoke the LangGraph agent:

```bash
source .venv/bin/activate
python - <<'PY'
import asyncio

from langchain_core.messages import HumanMessage
from eve_agent.agent import build_agent

async def main():
    agent = await build_agent()
    result = await agent.ainvoke({
        "messages": [
            HumanMessage(
                content=(
                    "Use the historical weather tool for latitude 34.05, "
                    "longitude -118.24, from 2024-08-01 to 2024-08-03. "
                    "Report daily maximum temperatures and precipitation "
                    "with units and identify the source."
                )
            )
        ]
    })
    print(result["messages"][-1].content)

asyncio.run(main())
PY
```

The graph has an assistant node and an MCP-backed tools node. The assistant
routes tool calls to the tools node, then runs again with the result; it stops
when the model returns a final answer. Tool definitions are loaded over
Streamable HTTP by [`eve_agent/mcp_client.py`](eve_agent/mcp_client.py).

## Run tests

From the repository root, with the requirements installed:

```bash
python3 -m unittest discover -s tests -v
```

Tests use mocked API responses and a scripted model, so they do not require
network access or a running Ollama instance.
