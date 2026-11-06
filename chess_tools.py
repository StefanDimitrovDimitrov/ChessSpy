"""Custom tool for the ChessSpy agent: fetch a chess.com player's games and summarize them.

The agent calls `get_player_stats`. Agno reads the function name, type hints and
docstring to build the tool schema the model sees, so keep the docstring accurate.
"""

import json
import logging
import re
from collections import Counter

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.chess.com/pub/player"
DEFAULT_HEADERS = {
    "User-Agent": "ChessSpy/1.0",
    "Accept": "application/json",
}
TIMEOUT = 10
MAX_MONTHS = 12

# chess.com result codes. "win" is the only winning code; everything below is a draw;
# anything else (checkmated, resigned, timeout, abandoned, lose, ...) is a loss.
DRAW_RESULTS = {
    "agreed",
    "repetition",
    "stalemate",
    "insufficient",
    "50move",
    "timevsinsufficient",
}


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def _get_json(url: str) -> dict:
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def download_games(username: str, months: int) -> list[dict]:
    """Return raw games from the player's last `months` monthly archives."""
    archives = _get_json(f"{BASE_URL}/{username}/games/archives").get("archives", [])
    games: list[dict] = []
    for archive_url in archives[-months:]:
        logger.info("Downloading %s", archive_url)
        games.extend(_get_json(archive_url).get("games", []))
    return games


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------
def opening_name(game: dict) -> str:
    """'https://www.chess.com/openings/Sicilian-Defense-Najdorf-Variation-6.Be3'
    -> 'Sicilian Defense Najdorf Variation'."""
    eco_url = game.get("eco")
    if not eco_url:
        return "Unknown"
    slug = eco_url.rstrip("/").split("/")[-1]
    slug = re.sub(r"-\d+\..*$", "", slug)  # drop the trailing move list, e.g. "-6.Be3"
    return slug.replace("-", " ") or "Unknown"


def outcome(result_code: str) -> str:
    if result_code == "win":
        return "win"
    if result_code in DRAW_RESULTS:
        return "draw"
    return "loss"


def clean_game(game: dict, username: str) -> dict:
    """Reduce a raw chess.com game to the fields we need, from `username`'s point of view."""
    is_white = game["white"]["username"].lower() == username.lower()
    me, opponent = (game["white"], game["black"]) if is_white else (game["black"], game["white"])
    return {
        "url": game.get("url"),
        "uuid": game.get("uuid"),
        "color": "white" if is_white else "black",
        "opponent": opponent["username"],
        "my_rating": me.get("rating"),
        "result": outcome(me["result"]),
        "time_class": game.get("time_class", "unknown"),
        "rated": game.get("rated", False),
        "opening": opening_name(game),
        "end_time": game.get("end_time"),
    }


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------
def _record(games: list[dict]) -> dict:
    counts = Counter(g["result"] for g in games)
    total = len(games)
    return {
        "games": total,
        "wins": counts["win"],
        "losses": counts["loss"],
        "draws": counts["draw"],
        "win_rate_pct": round(100 * counts["win"] / total, 1) if total else 0.0,
    }


def summarize(games: list[dict], top_n: int = 5) -> dict:
    by_color = {c: _record([g for g in games if g["color"] == c]) for c in ("white", "black")}
    time_classes = sorted({g["time_class"] for g in games})
    by_time_class = {tc: _record([g for g in games if g["time_class"] == tc]) for tc in time_classes}

    def top_openings(subset: list[dict]) -> list[dict]:
        counter = Counter(g["opening"] for g in subset)
        return [
            {"opening": name, **_record([g for g in subset if g["opening"] == name])}
            for name, _ in counter.most_common(top_n)
        ]

    opponents = Counter(g["opponent"] for g in games).most_common(3)
    ratings = sorted((g for g in games if g["my_rating"]), key=lambda g: g["end_time"] or 0)

    return {
        "overall": _record(games),
        "by_color": by_color,
        "by_time_class": by_time_class,
        "top_openings_as_white": top_openings([g for g in games if g["color"] == "white"]),
        "top_openings_as_black": top_openings([g for g in games if g["color"] == "black"]),
        "most_frequent_opponents": [{"opponent": o, "games": n} for o, n in opponents],
        "latest_rating": ratings[-1]["my_rating"] if ratings else None,
        "latest_rating_time_class": ratings[-1]["time_class"] if ratings else None,
    }


# ---------------------------------------------------------------------------
# The tool the agent calls
# ---------------------------------------------------------------------------
def get_player_stats(username: str, months: int = 3) -> str:
    """Fetch a chess.com player's recent games and return statistics about them.

    Use this whenever the user asks about a chess.com player: their wins, losses,
    draws, win rate, results with white or black, results per time control
    (bullet/blitz/rapid/daily), or which openings they play most.

    Args:
        username: The chess.com username, e.g. "hikaru".
        months: How many of the most recent months of games to analyse (1-12). Default 3.

    Returns:
        A JSON string with the statistics, or a JSON object with an "error" key.
    """
    username = username.strip()
    months = max(1, min(int(months), MAX_MONTHS))
    try:
        raw_games = download_games(username, months)
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return json.dumps({"error": f"chess.com player '{username}' was not found."})
        logger.exception("chess.com request failed")
        return json.dumps({"error": f"chess.com request failed: {e}"})
    except requests.exceptions.RequestException as e:
        logger.exception("chess.com request failed")
        return json.dumps({"error": f"Could not reach chess.com: {e}"})

    games = [clean_game(g, username) for g in raw_games]
    if not games:
        return json.dumps({"username": username, "months_analysed": months, "error": "No games found in this period."})

    return json.dumps({"username": username, "months_analysed": months, **summarize(games)})


if __name__ == "__main__":
    # Quick manual check without the agent: python chess_tools.py <username> [months]
    import sys

    logging.basicConfig(level=logging.INFO)
    name = sys.argv[1] if len(sys.argv) > 1 else "Stefan_Dimitrov"
    m = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    print(json.dumps(json.loads(get_player_stats(name, m)), indent=2))
