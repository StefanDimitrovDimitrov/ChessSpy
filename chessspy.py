"""ChessSpy: an Agno agent that analyses chess.com players, served by AgentOS (FastAPI).

Run:   python chessspy.py
Then:  http://localhost:7777/docs   (FastAPI / Swagger)
       https://os.agno.com          (AgentOS UI -> connect to http://localhost:7777)
"""

import os

from dotenv import load_dotenv

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.os import AgentOS
from agno.os.settings import AgnoAPISettings

from chess_tools import get_player_stats

load_dotenv()


# ---------------------------------------------------------------------------
# Model: free options (pick with MODEL_PROVIDER in .env)
# ---------------------------------------------------------------------------
def build_model():
    provider = os.getenv("MODEL_PROVIDER", "groq").lower()

    if provider == "groq":
        # Free tier, no credit card. Needs GROQ_API_KEY from https://console.groq.com
        from agno.models.groq import Groq

        return Groq(id=os.getenv("MODEL_ID", "openai/gpt-oss-120b"))

        # Fully local and free. Needs Ollama running and the model pulled:
        #   ollama pull qwen3:8b
        from agno.models.ollama import Ollama

        return Ollama(id=os.getenv("MODEL_ID", "qwen3:8b"))

    raise ValueError(f"Unknown MODEL_PROVIDER: {provider!r} (use 'groq' or 'ollama')")


# ---------------------------------------------------------------------------
# Storage: one SQLite file holds sessions (chat history) and user memories
# ---------------------------------------------------------------------------
db = SqliteDb(db_file="tmp/chessspy.db")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
chess_spy = Agent(
    id="chess-spy",
    name="ChessSpy",
    model=build_model(),
    db=db,
    tools=[get_player_stats],
    description="You are ChessSpy, an analyst who scouts chess.com players.",
    instructions=[
        "When the user asks about a chess.com player, ALWAYS call get_player_stats. Never invent statistics.",
        "If the user doesn't say how far back to look, use the default of 3 months.",
        "Present results with short markdown tables: overall record, by color, by time control, top openings.",
        "Point out one or two notable patterns, e.g. a weak opening or a big gap between white and black results.",
        "If the tool returns an error, explain it plainly and ask for a corrected username.",
        "Use the conversation history to answer follow-ups like 'and with black?' without re-fetching when the data is already there.",
    ],
    # --- conversation memory (stored in SQLite) ---
    add_history_to_context=True,  # send previous turns of this session to the model
    num_history_runs=5,           # how many previous turns
    # --- long-term memory about the user, across sessions ---
    update_memory_on_run=True,    # extract facts like "my username is X" after each run
    add_memories_to_context=True,
    add_datetime_to_context=True,
    markdown=True,
)


# ---------------------------------------------------------------------------
# AgentOS: wraps the agent in a FastAPI app
# ---------------------------------------------------------------------------
agent_os = AgentOS(
    id="chessspy-os",
    description="ChessSpy AgentOS",
    agents=[chess_spy],
    # When OS_SECURITY_KEY is set, every request needs "Authorization: Bearer <key>".
    # Always set it before exposing the app to the internet.
    settings=AgnoAPISettings(os_security_key=os.getenv("OS_SECURITY_KEY")),
)
app = agent_os.get_app()  # a normal FastAPI app; you can add your own routes to it


if __name__ == "__main__":
    agent_os.serve(app="chessspy:app", host="127.0.0.1", port=7777, reload=True)
