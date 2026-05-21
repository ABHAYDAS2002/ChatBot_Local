from datetime import datetime, UTC, timedelta, timezone
import json
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="AbhayAI")

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "chat_history.json"
TEMPLATE_FILE = BASE_DIR / "templates" / "index.html"
_file_lock = Lock()
IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_CHAT_TITLE = "New chat"

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    reply: str
    total_messages: int
    chat_id: str | None = None


class ChatSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


def _default_store() -> dict:
    return {"active_chat_id": None, "chats": []}


def _ensure_storage() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text(json.dumps(_default_store(), indent=2), encoding="utf-8")


def _read_store() -> dict:
    _ensure_storage()
    with _file_lock:
        try:
            raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = _default_store()
            DATA_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    # Backward compatibility: migrate old list-based history to one chat session.
    if isinstance(raw, list):
        migrated_chat_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        migrated_title = _derive_title(raw)
        migrated = {
            "active_chat_id": migrated_chat_id,
            "chats": [
                {
                    "id": migrated_chat_id,
                    "title": migrated_title,
                    "created_at": now,
                    "updated_at": now,
                    "messages": raw,
                }
            ],
        }
        _write_store(migrated)
        return migrated

    if not isinstance(raw, dict):
        return _default_store()

    raw.setdefault("active_chat_id", None)
    raw.setdefault("chats", [])

    updated = False
    for chat in raw["chats"]:
        title = chat.get("title", "")
        if not title or title == "Imported chat":
            chat["title"] = _derive_title(chat.get("messages", []))
            updated = True

    if updated:
        _write_store(raw)

    return raw


def _write_store(store: dict) -> None:
    with _file_lock:
        DATA_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _find_chat(store: dict, chat_id: str) -> dict | None:
    for chat in store.get("chats", []):
        if chat.get("id") == chat_id:
            return chat
    return None


def _create_chat(store: dict, title: str = DEFAULT_CHAT_TITLE) -> dict:
    now = datetime.now(UTC).isoformat()
    chat = {
        "id": str(uuid4()),
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    store.setdefault("chats", []).insert(0, chat)
    store["active_chat_id"] = chat["id"]
    return chat


def _derive_title(messages: list[dict]) -> str:
    first_user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    title = " ".join(first_user.split()).strip()
    if not title:
        return DEFAULT_CHAT_TITLE
    return title[:48] + ("..." if len(title) > 48 else "")


# ---------------------------------------------------------------------------
# Response helpers — each function handles one intent domain
# ---------------------------------------------------------------------------

def _name_response(lower: str) -> str | None:
    keywords = ("your name", "who are you", "what is your name", "what's your name")
    if any(k in lower for k in keywords):
        return "I am AbhayAI — a smart tech assistant built by Abhay, powered by FastAPI and React."
    return None


def _greeting_response(lower: str) -> str | None:
    if any(k in lower for k in ("good morning",)):
        return "Good morning! Hope your day is off to a great start. How can I help you?"
    if any(k in lower for k in ("good evening",)):
        return "Good evening! How can I assist you tonight?"
    if any(k in lower for k in ("good night",)):
        return "Good night! Rest well. See you next time."
    if any(k in lower for k in ("hello", "hi", "hey", "howdy")):
        return "Hello! I am your local AI agent. Ask me about Chennai, the time, or any general topic."
    if any(k in lower for k in ("thank you", "thanks", "thx")):
        return "You're welcome! Let me know if there's anything else I can help with."
    if any(k in lower for k in ("bye", "goodbye", "see you", "cya")):
        return "Goodbye! Come back anytime. Have a great day!"
    return None


def _help_response(lower: str) -> str | None:
    if any(k in lower for k in ("help", "what can you do", "capabilities", "features")):
        return (
            "I can help you with:\n"
            "• Chennai info — places, food, transport, weather, history, shopping\n"
            "• Current date/time (Chennai IST or server time)\n"
            "• Greetings and general conversation\n"
            "• Chat summary of recent messages\n"
            "• Basic general knowledge questions"
        )
    return None


def _time_response(lower: str) -> str | None:
    if "time in chennai" in lower or ("time" in lower and ("chennai" in lower or "chenna" in lower)):
        return f"Current time in Chennai is {datetime.now(IST).strftime('%I:%M %p')} IST."
    if "time" in lower:
        return f"Current server time is {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}."
    return None


def _chennai_date_response(lower: str) -> str | None:
    if "today" in lower or "date" in lower:
        return f"Today in Chennai is {datetime.now(IST).strftime('%A, %d %B %Y')} (IST)."
    return None


def _chennai_topic_response(lower: str) -> str | None:
    """Sub-topic responses within the Chennai domain."""
    if any(k in lower for k in ("food", "eat", "cuisine", "dish", "restaurant")):
        return (
            "Chennai is famous for its South Indian cuisine: Idli, Dosa, Filter Coffee, "
            "Chettinad Chicken, Pongal, Sambar, and Rasam. Popular food streets include "
            "Besant Nagar beach stalls, Murugan Idli Shop, and Saravana Bhavan."
        )
    if any(k in lower for k in ("transport", "travel", "metro", "bus", "train", "how to reach")):
        return (
            "Chennai has good transport options: CMRL Metro (two lines), MTC buses, "
            "local trains, auto-rickshaws, and app-based cabs (Ola, Uber). "
            "Chennai Central and Egmore are the main railway hubs."
        )
    if any(k in lower for k in ("weather", "climate", "temperature", "rain")):
        return (
            "Chennai has a tropical climate — hot and humid most of the year. "
            "Best time to visit is November to February (cooler and drier). "
            "The northeast monsoon brings heavy rains from October to December."
        )
    if any(k in lower for k in ("history", "historical", "origin", "founded", "old")):
        return (
            "Chennai (formerly Madras) was founded in 1639 by the British East India Company. "
            "It has a rich history including St. George Fort, the oldest English fortress in India, "
            "and significant ties to South Indian classical music and Bharatanatyam dance."
        )
    if any(k in lower for k in ("shop", "mall", "market", "buy")):
        return (
            "Top shopping spots in Chennai: Express Avenue Mall, Phoenix MarketCity, "
            "T. Nagar (Ranganathan Street for traditional wear), Pondy Bazaar, "
            "and Spencer Plaza."
        )
    if any(k in lower for k in ("sport", "cricket", "ipl", "football", "stadium")):
        return (
            "Chennai loves cricket! The MA Chidambaram Stadium (Chepauk) is one of India's oldest. "
            "Chennai Super Kings (CSK) is the IPL team based here. "
            "Jawaharlal Nehru Stadium hosts football and athletics events."
        )
    if any(k in lower for k in ("place", "visit", "tourist", "attraction", "see")):
        return (
            "Top places to visit in Chennai: Marina Beach, Kapaleeshwarar Temple, "
            "Santhome Cathedral Basilica, Government Museum, Fort St. George, "
            "Besant Nagar (Elliot's) Beach, Valluvar Kottam, and DakshinaChitra."
        )
    if any(k in lower for k in ("tell about", "about chennai", "what is chennai", "overview")):
        return (
            "Chennai is the capital of Tamil Nadu and a major South Indian metropolis. "
            "Known for its Dravidian temples, classical arts (Carnatic music, Bharatanatyam), "
            "Marina Beach (world's second longest), and thriving IT and automobile industries."
        )
    return None


def _chennai_response(lower: str) -> str | None:
    if "chennai" not in lower and "chenna" not in lower:
        return None

    date_reply = _chennai_date_response(lower)
    if date_reply:
        return date_reply

    topic_reply = _chennai_topic_response(lower)
    if topic_reply:
        return topic_reply

    return (
        "Chennai is a vibrant coastal city in South India. "
        "Ask me about Chennai's food, weather, transport, history, shopping, sports, or places to visit!"
    )


def _general_response(lower: str) -> str | None:
    if any(k in lower for k in ("capital of india", "capital of tamil nadu")):
        if "tamil nadu" in lower:
            return "The capital of Tamil Nadu is Chennai."
        return "The capital of India is New Delhi."
    if any(k in lower for k in ("joke", "funny", "make me laugh")):
        return "Why do programmers prefer dark mode? Because light attracts bugs! 😄"
    if any(k in lower for k in ("meaning of life", "42")):
        return "The meaning of life is 42 — at least according to The Hitchhiker's Guide to the Galaxy!"
    return None


def _summary_response(lower: str, history: list[dict]) -> str | None:
    if "summary" in lower or "summarize" in lower:
        recent = [m["content"] for m in history if m.get("role") == "user"][-3:]
        if not recent:
            return "No prior user messages found yet."
        return "Quick summary of your latest topics: " + " | ".join(recent)
    return None


# ---------------------------------------------------------------------------
# Main dispatcher — runs each helper in priority order
# ---------------------------------------------------------------------------

def _agent_reply(user_message: str, history: list[dict]) -> str:
    text = user_message.strip()
    lower = text.lower()

    for fn in (
        lambda l: _name_response(l),
        lambda l: _greeting_response(l),
        lambda l: _help_response(l),
        lambda l: _time_response(l),
        lambda l: _chennai_response(l),
        lambda l: _general_response(l),
        lambda l: _summary_response(l, history),
    ):
        result = fn(lower)
        if result:
            return result

    return (
        f"I received: '{text}'. "
        "I am a local rule-based agent. Try asking about Chennai, the time, or type 'help' to see what I can do."
    )


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    if TEMPLATE_FILE.exists():
        return TEMPLATE_FILE.read_text(encoding="utf-8")
    return "<h1>Frontend file not found.</h1>"


@app.get("/api/history")
def get_history() -> dict:
    store = _read_store()
    active_id = store.get("active_chat_id")
    chat = _find_chat(store, active_id) if active_id else None
    return {"messages": chat.get("messages", []) if chat else [], "chat_id": active_id}


@app.get("/api/chats")
def list_chats() -> dict:
    store = _read_store()
    summaries = [
        ChatSummary(
            id=chat["id"],
            title=chat.get("title", DEFAULT_CHAT_TITLE),
            created_at=chat.get("created_at", ""),
            updated_at=chat.get("updated_at", ""),
            message_count=len(chat.get("messages", [])),
        ).model_dump()
        for chat in store.get("chats", [])
    ]
    return {"chats": summaries, "active_chat_id": store.get("active_chat_id")}


@app.post("/api/chats")
def create_chat() -> dict:
    store = _read_store()
    chat = _create_chat(store)
    _write_store(store)
    return {"chat": chat, "active_chat_id": store.get("active_chat_id")}


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str) -> dict:
    store = _read_store()
    chat = _find_chat(store, chat_id)
    if not chat:
        return {"chat": None}
    store["active_chat_id"] = chat_id
    _write_store(store)
    return {"chat": chat, "active_chat_id": chat_id}


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str) -> dict:
    store = _read_store()
    chats = store.get("chats", [])
    remaining = [chat for chat in chats if chat.get("id") != chat_id]

    if len(remaining) == len(chats):
        return {"status": "not_found", "active_chat_id": store.get("active_chat_id")}

    store["chats"] = remaining
    if store.get("active_chat_id") == chat_id:
        store["active_chat_id"] = remaining[0]["id"] if remaining else None

    _write_store(store)
    return {"status": "deleted", "active_chat_id": store.get("active_chat_id")}


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    store = _read_store()
    active_id = store.get("active_chat_id")
    active_chat = _find_chat(store, active_id) if active_id else None
    if not active_chat:
        active_chat = _create_chat(store)

    history = active_chat["messages"]
    timestamp = datetime.now(UTC).isoformat()

    user_entry = {
        "role": "user",
        "content": payload.message.strip(),
        "timestamp": timestamp,
    }
    history.append(user_entry)

    reply_text = _agent_reply(payload.message, history)
    bot_entry = {
        "role": "assistant",
        "content": reply_text,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    history.append(bot_entry)

    active_chat["updated_at"] = datetime.now(UTC).isoformat()
    active_chat["title"] = _derive_title(history)
    store["active_chat_id"] = active_chat["id"]

    _write_store(store)
    return ChatResponse(reply=reply_text, total_messages=len(history), chat_id=active_chat["id"])


@app.post("/api/chats/{chat_id}/messages", response_model=ChatResponse)
def chat_in_session(chat_id: str, payload: ChatRequest) -> ChatResponse:
    store = _read_store()
    chat = _find_chat(store, chat_id)
    if not chat:
        chat = _create_chat(store)
        chat_id = chat["id"]

    history = chat["messages"]
    timestamp = datetime.now(UTC).isoformat()

    user_entry = {
        "role": "user",
        "content": payload.message.strip(),
        "timestamp": timestamp,
    }
    history.append(user_entry)

    reply_text = _agent_reply(payload.message, history)
    bot_entry = {
        "role": "assistant",
        "content": reply_text,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    history.append(bot_entry)

    chat["updated_at"] = datetime.now(UTC).isoformat()
    chat["title"] = _derive_title(history)
    store["active_chat_id"] = chat_id

    _write_store(store)
    return ChatResponse(reply=reply_text, total_messages=len(history), chat_id=chat_id)


@app.delete("/api/history")
def clear_history() -> dict:
    store = _read_store()
    active_id = store.get("active_chat_id")
    active_chat = _find_chat(store, active_id) if active_id else None
    if active_chat:
        active_chat["messages"] = []
        active_chat["title"] = DEFAULT_CHAT_TITLE
        active_chat["updated_at"] = datetime.now(UTC).isoformat()
        _write_store(store)
    return {"status": "cleared", "chat_id": active_id}
