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
```

The `.env` file sets `API_HOST` and `API_PORT` (defaults `127.0.0.1` and
`8000`), `MCP_SERVER_HOST` and `MCP_SERVER_PORT` (defaults `127.0.0.1` and
`8001`), and `OLLAMA_MODEL` (default `qwen3.5:4b`). The MCP client uses the
server settings to connect at `http://<host>:<port>/mcp`. `TRACE_FILE` selects
the JSONL request trace path and defaults to `logs/agent-traces.jsonl`. `.env`
is ignored by Git; commit only the non-sensitive `.env.example` template.

## Run the API

Pull the configured model if it is not already installed:

```bash
ollama pull qwen3.5:4b
```

Start the MCP server in one terminal from the repository root:

```bash
source .venv/bin/activate
python -m eve_agent.mcp_server
```

Start the HTTP API in another terminal:

```bash
source .venv/bin/activate
python -m eve_agent.api
```

Send a question and a follow-up with the same `session_id`:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-session","message":"What was the weather in Los Angeles from 2024-08-01 to 2024-08-03?"}'

curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-session","message":"What was the precipitation over the same dates?"}'
```

Each successful request returns JSON with `session_id` and `answer`.

## Run the end-to-end demo

With the MCP server and API running in separate terminals as described above,
run:

```bash
source .venv/bin/activate
python -m scripts.run_demo
```

The demo creates one session and sends three requests: a historical weather
question that calls Open-Meteo, a follow-up that relies on the same location
and dates without repeating them, and a request with an invalid date that
forces a tool error. The API prints its answers and writes one trace record
per request to `TRACE_FILE`.

[`examples/traces/stage8-demo.jsonl`](./examples/traces/stage8-demo.jsonl) is a
sample live run. Its three records share a session ID: the first includes the
weather tool call, the second has no tool step and uses the prior context, and
the third records the invalid-date error and the agent's reply. Normal API
requests write to the ignored `logs/agent-traces.jsonl` by default, not to
this committed sample.

The graph has an assistant node and an MCP-backed tools node. The assistant
routes tool calls to the tools node, then runs again with the result; it stops
when the model returns a final answer. Tool definitions are loaded over
Streamable HTTP by [`eve_agent/mcp_client.py`](eve_agent/mcp_client.py).

The API builds one agent graph at startup. Send the same `session_id` for
follow-up questions in that process; use a different ID for a separate
conversation. The agent retains the latest six user turns (including their
assistant and tool messages) and truncates each tool result to at most 8,000
characters before passing it back to the model.

Conversation checkpoints use LangGraph's in-memory `MemorySaver`. They are
available only to that agent instance and are lost when the process exits.
Persistent or multi-process deployments need a database-backed LangGraph
checkpointer.

## Traces and tool errors

Each `/chat` request appends one JSON record to the file configured by
`TRACE_FILE`. The trace includes the session and trace IDs, input, graph steps,
tool names and arguments, durations, tool results or errors, and final answer.
Tool result text in traces is capped at 8,000 characters. Tool exceptions are
returned to the graph as tool errors so the agent can explain the failure;
the error is recorded in the request trace. The default `logs/` directory is
Git-ignored. Traces contain conversation input and tool data, so keep them
local unless you have checked their contents before sharing.

## Run tests

From the repository root, with the requirements installed:

```bash
python3 -m unittest discover -s tests -v
```

Tests use mocked API responses and a scripted model, so they do not require
network access or a running Ollama instance.

## Scope and next steps

This submission keeps the required core to one agent, two MCP tools, and
process-local in-memory conversation state. The API has no authentication or
rate limiting, and the optional A2A and Agent Skills bonuses are not
implemented. For a deployed service, the next steps would be a persistent
database-backed checkpointer, API access controls, and operational monitoring.
