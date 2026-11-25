"""Run the required three-turn Earth Observation agent demo."""

import argparse
import json
from urllib.request import Request, urlopen
from uuid import uuid4

from eve_agent.settings import API_HOST, API_PORT

TURNS = (
    "Use NASA EONET to find two open wildfire-category events in this bounding "
    "box: min_lon=-83, max_lat=39, max_lon=-78, min_lat=36. Set the result "
    "limit to 2 and include each event title and point coordinates.",
    "For the second event you found, use its point coordinates to get Open-Meteo "
    "daily maximum temperature and precipitation from 2024-08-01 through "
    "2024-08-03. Include the event title, coordinates, units, and source.",
    "Use the historical weather tool for that same event location from "
    "2024-99-99 through 2024-99-99. If it fails, explain that the weather "
    "couldn't be retrieved and ask me for valid YYYY-MM-DD dates. Don't invent "
    "weather values.",
)

LONG_CONTEXT_TURNS = (
    *TURNS,
    "For the successful valid-date weather lookup, what was the total "
    "precipitation on those dates?",
    "Which date had the highest daily maximum temperature in that lookup?",
    "How much warmer was the hottest date than August 1?",
    "Which date was coolest? Also, restate the complete successful weather "
    "lookup with all daily temperatures and precipitation, and remind me of "
    "the title and coordinates reported for the second EONET event.",
    "Using the weather results you just restated, summarize the hottest date "
    "and temperature and total precipitation.",
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--long-context",
        action="store_true",
        help="run eight turns to demonstrate conversation pruning",
    )
    args = parser.parse_args()
    turns = LONG_CONTEXT_TURNS if args.long_context else TURNS
    session_id = f"stage8-demo-{uuid4().hex[:8]}"
    print(f"Session: {session_id}")
    for turn_number, message in enumerate(turns, start=1):
        print(f"\nTurn {turn_number}: {message}")
        print(f"Answer: {_ask_agent(session_id, message)}")


if __name__ == "__main__":
    main()
