"""Run the required three-turn Earth Observation agent demo."""

import json
from urllib.request import Request, urlopen
from uuid import uuid4

from eve_agent.settings import API_HOST, API_PORT

TURNS = (
    "Use the historical weather tool to report daily maximum temperature and "
    "total precipitation at latitude 34.05, longitude -118.24, from "
    "2024-08-01 through 2024-08-03. Include units and identify the source.",
    "What was the total precipitation on those same dates at that same location?",
    "Use the historical weather tool to query that same location from "
    "2024-99-99 through 2024-99-99. Return the exact tool error only; do not "
    "infer validation behavior beyond the error text.",
)


def _ask_agent(session_id: str, message: str) -> str:
    request = Request(
        f"http://{API_HOST}:{API_PORT}/chat",
        data=json.dumps({"session_id": session_id, "message": message}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=180) as response:
        result = json.load(response)
    answer = result["answer"]
    if not isinstance(answer, str):
        raise TypeError("The chat API returned a non-text answer")
    return answer


def main() -> None:
    session_id = f"stage8-demo-{uuid4().hex[:8]}"
    print(f"Session: {session_id}")
    for turn_number, message in enumerate(TURNS, start=1):
        print(f"\nTurn {turn_number}: {message}")
        print(f"Answer: {_ask_agent(session_id, message)}")


if __name__ == "__main__":
    main()
