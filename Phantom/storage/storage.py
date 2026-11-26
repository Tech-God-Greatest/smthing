import sqlite3
import json
import os
import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT_DIR, "chat_history.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT DEFAULT 'New Chat'
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        role TEXT,
        content TEXT
    );
    """)

    cursor.execute("PRAGMA table_info(chats);")
    chats_cols = [row["name"] for row in cursor.fetchall()]

    if "summary" not in chats_cols:
        cursor.execute("ALTER TABLE chats ADD COLUMN summary TEXT DEFAULT '';")
    if "created_at" not in chats_cols:
        cursor.execute("ALTER TABLE chats ADD COLUMN created_at TIMESTAMP;")
    if "updated_at" not in chats_cols:
        cursor.execute("ALTER TABLE chats ADD COLUMN updated_at TIMESTAMP;")
    if "message_count" not in chats_cols:
        cursor.execute("ALTER TABLE chats ADD COLUMN message_count INTEGER DEFAULT 0;")
    if "is_archived" not in chats_cols:
        cursor.execute("ALTER TABLE chats ADD COLUMN is_archived INTEGER DEFAULT 0;")

    cursor.execute("PRAGMA table_info(messages);")
    messages_cols = [row["name"] for row in cursor.fetchall()]

    if "token_count" not in messages_cols:
        cursor.execute("ALTER TABLE messages ADD COLUMN token_count INTEGER DEFAULT 0;")
    if "timestamp" not in messages_cols:
        cursor.execute("ALTER TABLE messages ADD COLUMN timestamp TIMESTAMP;")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE chats SET created_at = ? WHERE created_at IS NULL", (now,))
    cursor.execute("UPDATE chats SET updated_at = ? WHERE updated_at IS NULL", (now,))
    cursor.execute("UPDATE messages SET timestamp = ? WHERE timestamp IS NULL", (now,))

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_title ON chats(title);")

    conn.commit()
    conn.close()


def create_chat(title="New Chat") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO chats (title, summary, created_at, updated_at, message_count, is_archived) VALUES (?, '', ?, ?, 0, 0)",
        (title, now, now)
    )
    chat_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return chat_id


def update_chat_title(chat_id: int, title: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
        (title, now, chat_id)
    )
    conn.commit()
    conn.close()


def update_chat_summary(chat_id: int, summary: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE chats SET summary = ?, updated_at = ? WHERE id = ?",
        (summary, now, chat_id)
    )
    conn.commit()
    conn.close()


def archive_chat(chat_id: int, is_archived: bool = True):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE chats SET is_archived = ?, updated_at = ? WHERE id = ?",
        (1 if is_archived else 0, now, chat_id)
    )
    conn.commit()
    conn.close()


def delete_chat(chat_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    conn.commit()
    conn.close()


def save_message(chat_id: int, role: str, content: str, token_count: int = 0) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO messages (chat_id, role, content, token_count, timestamp) VALUES (?, ?, ?, ?, ?)",
        (chat_id, role, content, token_count, now)
    )
    msg_id = cursor.lastrowid
    cursor.execute(
        "UPDATE chats SET message_count = message_count + 1, updated_at = ? WHERE id = ?",
        (now, chat_id)
    )
    conn.commit()
    conn.close()
    return msg_id


def get_recent_messages(chat_id: int, limit: int = 50) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT role, content, token_count, timestamp
        FROM (
            SELECT id, role, content, token_count, timestamp
            FROM messages
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
        )
        ORDER BY id ASC
        """,
        (chat_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"], "token_count": r["token_count"], "timestamp": r["timestamp"]} for r in rows]


def get_chat_summary(chat_id: int) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT summary FROM chats WHERE id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return row["summary"] if row and row["summary"] else ""


def list_chats(search_query: str = "", show_archived: bool = False) -> list:
    conn = get_connection()
    cursor = conn.cursor()

    archived_clause = "1=1" if show_archived else "(is_archived = 0 OR is_archived IS NULL)"

    if search_query.strip():
        q = f"%{search_query.strip()}%"
        cursor.execute(
            f"""
            SELECT DISTINCT c.id, c.title, c.summary, c.created_at, c.updated_at, c.message_count, c.is_archived
            FROM chats c
            LEFT JOIN messages m ON c.id = m.chat_id
            WHERE {archived_clause} AND (c.title LIKE ? OR m.content LIKE ?)
            ORDER BY c.updated_at DESC
            """,
            (q, q)
        )
    else:
        cursor.execute(
            f"""
            SELECT id, title, summary, created_at, updated_at, message_count, is_archived
            FROM chats
            WHERE {archived_clause}
            ORDER BY updated_at DESC
            """
        )

    rows = cursor.fetchall()
    conn.close()

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chats = []
    for r in rows:
        chats.append({
            "id": r["id"],
            "title": r["title"] or "New Chat",
            "summary": r["summary"] or "",
            "created_at": r["created_at"] or now_str,
            "updated_at": r["updated_at"] or now_str,
            "message_count": r["message_count"] or 0,
            "is_archived": r["is_archived"] or 0
        })
    return chats


def export_chat(chat_id: int, export_format: str = "json") -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title, summary, created_at FROM chats WHERE id = ?", (chat_id,))
    chat_row = cursor.fetchone()
    if not chat_row:
        conn.close()
        return ""

    title = chat_row["title"]
    cursor.execute("SELECT role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY id ASC", (chat_id,))
    msg_rows = cursor.fetchall()
    conn.close()

    messages = [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in msg_rows]

    if export_format.lower() == "json":
        return json.dumps({
            "title": title,
            "summary": chat_row["summary"],
            "created_at": chat_row["created_at"],
            "messages": messages
        }, indent=2)
    elif export_format.lower() == "md":
        lines = [f"# {title}", f"*Created at: {chat_row['created_at']}*", ""]
        if chat_row["summary"]:
            lines.extend([f"**Summary**: {chat_row['summary']}", ""])
        lines.append("---")
        for m in messages:
            role_name = "User" if m["role"] == "user" else "Phantom"
            lines.append(f"### {role_name} ({m['timestamp']})")
            lines.append(m["content"])
            lines.append("")
        return "\n".join(lines)
    else:
        lines = [f"=== {title} ===", f"Created: {chat_row['created_at']}\n"]
        for m in messages:
            role_name = "You" if m["role"] == "user" else "Phantom"
            lines.append(f"[{m['timestamp']}] {role_name}:\n{m['content']}\n")
        return "\n".join(lines)


def save_memory(content: str):
    """Backwards-compatibility helper for saving memories."""
    try:
        from tools import memory_tools
        memory_tools.remember("general", "preference", str(content))
    except Exception:
        pass


# Backwards compatibility alias
add_message = save_message

