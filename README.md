# ChessSpy

An Agno agent that scouts chess.com players. Ask "How does hikaru play?" and it fetches the
player's recent games, then reports wins/losses/draws, results by color and time control, and
the openings they play most.

- **Model:** Groq free tier (cloud) or Ollama (local), switched with `MODEL_PROVIDER`
- **Memory:** SQLite (`tmp/chessspy.db`), holding chat history per session plus long-term user memories
- **API:** AgentOS, a FastAPI app on `http://localhost:7777`
- **Public access:** Cloudflare Tunnel (formerly "Argo Tunnel")

## Files

| File | What it does |
|---|---|
| `chess_tools.py` | The custom tool `get_player_stats(username, months=3)`: download, clean, summarize |
| `chessspy.py` | Agent + SQLite + AgentOS app |
| `.env.example` | Settings to copy into `.env` |

## 1. Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in the keys
```

**Option A, Groq (recommended to start):** sign up at https://console.groq.com, create an API
key, and put it in `GROQ_API_KEY`. The free tier is rate-limited (on the 70B model roughly 30
requests/min and about 100K tokens/day). The tool returns compact stats rather than raw games,
so it stays well inside that.

**Option B, Ollama (fully offline):** install from https://ollama.com, then:
```bash
ollama pull qwen3:8b
```
and set `MODEL_PROVIDER=ollama`. Choose a model that supports tool calling; small models
call tools less reliably.

## 2. Test the tool on its own

```bash
python chess_tools.py Stefan_Dimitrov 1
```

## 3. Run the agent

```bash
python chessspy.py
```

- Swagger UI: http://localhost:7777/docs
- Chat UI: open https://os.agno.com, choose **Add OS**, and enter `http://localhost:7777`.
  The page runs in your browser, so it can reach your localhost.

Call it from the API directly:

```bash
curl -X POST http://localhost:7777/agents/chess-spy/runs \
  -H "Authorization: Bearer $OS_SECURITY_KEY" \
  -F "message=Scout Stefan_Dimitrov for the last 2 months" \
  -F "stream=false" \
  -F "session_id=s1" -F "user_id=stefan"
```

Send a follow-up with the **same `session_id`**, for example `-F "message=And how does he do with black?"`,
and the agent answers from the history stored in SQLite. Reuse the same `user_id` in a new session and it
still remembers facts it learned about you, such as your own username.

## 4. Expose it on the web with Cloudflare Tunnel

The app keeps running on your computer. Cloudflare gives it a public HTTPS URL, and you don't need to
open router ports.

**Set `OS_SECURITY_KEY` in `.env` first.** Without it, anyone with the URL can use your Groq quota.

Install `cloudflared` (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

**Quick tunnel (no account, random URL that changes on each start):**
```bash
cloudflared tunnel --url http://localhost:7777
# prints something like https://random-words.trycloudflare.com
```

**Named tunnel (stable URL on your own domain, needs a free Cloudflare account with a domain):**
```bash
cloudflared tunnel login
cloudflared tunnel create chessspy
cloudflared tunnel route dns chessspy chessspy.yourdomain.com
cloudflared tunnel run --url http://localhost:7777 chessspy
```

Then call `https://<your-url>/agents/chess-spy/runs` with the `Authorization: Bearer` header,
or add that URL in os.agno.com.
