import sqlite3
import os
import json
from datetime import datetime
from typing import Iterable

DB_PATH = os.path.join(os.path.dirname(__file__), 'astral.db')

TAG_ALIAS_MAP = {
    "mean reversion": "mean-reversion",
    "mean_reversion": "mean-reversion",
    "trend following": "trend-following",
    "trend_following": "trend-following",
}


def normalize_tags(tags: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for raw_tag in tags or []:
        tag = str(raw_tag).strip().lower()
        if not tag:
            continue
        tag = TAG_ALIAS_MAP.get(tag, tag)
        if tag not in seen:
            seen.add(tag)
            normalized.append(tag)

    return normalized

def init_db():
    """Initializes the SQLite database with required tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # User Preferences & API Keys
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY DEFAULT 1,
        api_keys TEXT, -- JSON blob of encrypted API keys
        theme TEXT DEFAULT 'dark',
        paper_trading BOOLEAN DEFAULT 1,
        risk_live_trading_enabled BOOLEAN DEFAULT 0,
        risk_max_order_notional REAL DEFAULT 1000.0,
        risk_max_position_pct REAL DEFAULT 25.0
    )
    ''')

    existing_settings_columns = {row[1] for row in cursor.execute("PRAGMA table_info(settings)").fetchall()}
    settings_column_migrations = {
        "risk_live_trading_enabled": "ALTER TABLE settings ADD COLUMN risk_live_trading_enabled BOOLEAN DEFAULT 0",
        "risk_max_order_notional": "ALTER TABLE settings ADD COLUMN risk_max_order_notional REAL DEFAULT 1000.0",
        "risk_max_position_pct": "ALTER TABLE settings ADD COLUMN risk_max_position_pct REAL DEFAULT 25.0",
    }
    for column, statement in settings_column_migrations.items():
        if column not in existing_settings_columns:
            cursor.execute(statement)

    # Saved Strategies
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS strategies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        code TEXT,
        symbol TEXT,
        asset_type TEXT,
        tags TEXT DEFAULT '[]',
        builder_graph TEXT DEFAULT '{}',
        validation_summary TEXT DEFAULT '{}',
        optimization_summary TEXT DEFAULT '{}',
        is_baseline BOOLEAN DEFAULT 0,
        is_archived BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    existing_strategy_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(strategies)").fetchall()
    }
    strategy_column_migrations = {
        "symbol": "ALTER TABLE strategies ADD COLUMN symbol TEXT",
        "asset_type": "ALTER TABLE strategies ADD COLUMN asset_type TEXT",
        "tags": "ALTER TABLE strategies ADD COLUMN tags TEXT DEFAULT '[]'",
        "builder_graph": "ALTER TABLE strategies ADD COLUMN builder_graph TEXT DEFAULT '{}'",
        "validation_summary": "ALTER TABLE strategies ADD COLUMN validation_summary TEXT DEFAULT '{}'",
        "optimization_summary": "ALTER TABLE strategies ADD COLUMN optimization_summary TEXT DEFAULT '{}'",
        "is_baseline": "ALTER TABLE strategies ADD COLUMN is_baseline BOOLEAN DEFAULT 0",
        "is_archived": "ALTER TABLE strategies ADD COLUMN is_archived BOOLEAN DEFAULT 0",
    }
    for column, statement in strategy_column_migrations.items():
        if column not in existing_strategy_columns:
            cursor.execute(statement)

    # Trade History (Paper or Live)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        side TEXT,
        qty REAL,
        price REAL,
        broker_id TEXT DEFAULT 'paper',
        execution_mode TEXT DEFAULT 'paper',
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_paper BOOLEAN DEFAULT 1
    )
    ''')

    # Chat History (AI Conversations)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT,
        role TEXT,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    existing_trade_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(trades)").fetchall()
    }
    trade_column_migrations = {
        "broker_id": "ALTER TABLE trades ADD COLUMN broker_id TEXT DEFAULT 'paper'",
        "execution_mode": "ALTER TABLE trades ADD COLUMN execution_mode TEXT DEFAULT 'paper'",
        "order_status": "ALTER TABLE trades ADD COLUMN order_status TEXT DEFAULT 'filled'",
        "order_type": "ALTER TABLE trades ADD COLUMN order_type TEXT DEFAULT 'market'",
        "broker_order_id": "ALTER TABLE trades ADD COLUMN broker_order_id TEXT",
        "is_test": "ALTER TABLE trades ADD COLUMN is_test BOOLEAN DEFAULT 0",
        "metadata": "ALTER TABLE trades ADD COLUMN metadata TEXT DEFAULT '{}'",
    }
    for column, statement in trade_column_migrations.items():
        if column not in existing_trade_columns:
            cursor.execute(statement)

    # Ensure a default settings row exists
    cursor.execute("INSERT OR IGNORE INTO settings (id, api_keys, theme, paper_trading) VALUES (1, '{}', 'dark', 1)")
    
    conn.commit()
    conn.close()

def get_settings():
    """Return internal settings, including secrets. Never log this object."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, api_keys, theme, paper_trading,
                   risk_live_trading_enabled, risk_max_order_notional, risk_max_position_pct
            FROM settings WHERE id=1
        """)
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0],
                "api_keys": json.loads(row[1] or "{}"),
                "theme": row[2],
                "paper_trading": bool(row[3]),
                "risk_live_trading_enabled": bool(row[4]),
                "risk_max_order_notional": float(row[5] or 1000.0),
                "risk_max_position_pct": float(row[6] or 25.0),
            }
    except sqlite3.Error:
        return None
    return None


def get_public_settings():
    settings = get_settings()
    if not settings:
        return None
    public = dict(settings)
    public["api_keys"] = {
        key: ("********" if value else "")
        for key, value in settings.get("api_keys", {}).items()
    }
    return public


def update_settings(
    api_keys: dict = None,
    theme: str = None,
    paper_trading: bool = None,
    risk_live_trading_enabled: bool = None,
    risk_max_order_notional: float = None,
    risk_max_position_pct: float = None,
):
    current = get_settings()
    if not current:
        return False
    max_notional = (
        float(risk_max_order_notional)
        if risk_max_order_notional is not None
        else current["risk_max_order_notional"]
    )
    if max_notional <= 0:
        raise ValueError("risk_max_order_notional must be positive")
    max_position_pct = (
        float(risk_max_position_pct)
        if risk_max_position_pct is not None
        else current["risk_max_position_pct"]
    )
    if not 0 < max_position_pct <= 100:
        raise ValueError("risk_max_position_pct must be between 0 and 100")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE settings
        SET api_keys = ?, theme = ?, paper_trading = ?,
            risk_live_trading_enabled = ?, risk_max_order_notional = ?, risk_max_position_pct = ?
        WHERE id = 1
    """, (
        json.dumps(api_keys if api_keys is not None else current["api_keys"]),
        theme if theme is not None else current["theme"],
        int(paper_trading) if paper_trading is not None else int(current["paper_trading"]),
        int(risk_live_trading_enabled) if risk_live_trading_enabled is not None else int(current["risk_live_trading_enabled"]),
        max_notional,
        max_position_pct,
    ))
    conn.commit()
    conn.close()
    return True

def record_trade(
    symbol: str,
    side: str,
    qty: float,
    price: float,
    is_paper: bool = True,
    broker_id: str = "paper",
    execution_mode: str = "paper",
    order_status: str = "filled",
    order_type: str = "market",
    broker_order_id: str | None = None,
    is_test: bool = False,
    metadata: dict | None = None,
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO trades (symbol, side, qty, price, broker_id, execution_mode, is_paper, order_status, order_type, broker_order_id, is_test, metadata)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        symbol,
        side,
        qty,
        price,
        broker_id,
        execution_mode,
        int(is_paper),
        order_status,
        order_type,
        broker_order_id,
        int(is_test),
        json.dumps(metadata or {}),
    ))
    conn.commit()
    conn.close()
    return True

def record_chat_message(conversation_id: str, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO chat_logs (conversation_id, role, content)
        VALUES (?, ?, ?)
        ''',
        (conversation_id, role, content),
    )
    conn.commit()
    conn.close()
    return True

def get_recent_chat_messages(conversation_id: str, limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT role, content, created_at
        FROM chat_logs
        WHERE conversation_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        ''',
        (conversation_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    items = [
        {"role": role, "content": content, "created_at": created_at}
        for role, content, created_at in rows
    ]
    items.reverse()
    return items

def get_trades(limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, symbol, side, qty, price, broker_id, execution_mode, timestamp, is_paper, order_status, order_type, broker_order_id, is_test, metadata
        FROM trades
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "symbol": r[1],
            "side": r[2],
            "qty": r[3],
            "price": r[4],
            "broker_id": r[5],
            "execution_mode": r[6],
            "timestamp": r[7],
            "is_paper": bool(r[8]),
            "order_status": r[9] or "unknown",
            "order_type": r[10] or "market",
            "broker_order_id": r[11],
            "is_test": bool(r[12]),
            "metadata": json.loads(r[13] or '{}'),
        } for r in rows
    ]

def get_trade_by_id(trade_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, symbol, side, qty, price, broker_id, execution_mode, timestamp, is_paper, order_status, order_type, broker_order_id, is_test, metadata
        FROM trades
        WHERE id = ?
        """,
        (trade_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "symbol": row[1],
        "side": row[2],
        "qty": row[3],
        "price": row[4],
        "broker_id": row[5],
        "execution_mode": row[6],
        "timestamp": row[7],
        "is_paper": bool(row[8]),
        "order_status": row[9] or "unknown",
        "order_type": row[10] or "market",
        "broker_order_id": row[11],
        "is_test": bool(row[12]),
        "metadata": json.loads(row[13] or '{}'),
    }

def update_trade_order_state(
    trade_id: int,
    order_status: str,
    broker_order_id: str | None = None,
    metadata: dict | None = None,
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE trades
        SET order_status = ?, broker_order_id = COALESCE(?, broker_order_id), metadata = ?, timestamp = timestamp
        WHERE id = ?
        """,
        (order_status, broker_order_id, json.dumps(metadata or {}), trade_id),
    )
    conn.commit()
    conn.close()
    return True

def save_strategy(
    name: str,
    code: str,
    symbol: str = "",
    asset_type: str = "crypto",
    tags: list[str] | None = None,
    builder_graph: dict | None = None,
    validation_summary: dict | None = None,
    optimization_summary: dict | None = None,
    is_baseline: bool = False,
    strategy_id: int | None = None,
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    tags_json = json.dumps(normalize_tags(tags))
    graph_json = json.dumps(builder_graph or {})
    validation_json = json.dumps(validation_summary or {})
    optimization_json = json.dumps(optimization_summary or {})

    if is_baseline:
        cursor.execute("UPDATE strategies SET is_baseline = 0")

    if strategy_id:
        cursor.execute(
            '''
            UPDATE strategies
            SET name = ?, code = ?, symbol = ?, asset_type = ?, tags = ?, builder_graph = ?, validation_summary = ?, optimization_summary = ?, is_baseline = ?, last_modified = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (name, code, symbol, asset_type, tags_json, graph_json, validation_json, optimization_json, int(is_baseline), strategy_id),
        )
    else:
        cursor.execute(
            '''
            INSERT INTO strategies (name, code, symbol, asset_type, tags, builder_graph, validation_summary, optimization_summary, is_baseline)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (name, code, symbol, asset_type, tags_json, graph_json, validation_json, optimization_json, int(is_baseline)),
        )
        strategy_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return strategy_id

def get_strategies(limit: int = 50, include_archived: bool = False, archived_only: bool = False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    where_clause = ""
    if archived_only:
        where_clause = "WHERE is_archived = 1"
    elif not include_archived:
        where_clause = "WHERE is_archived = 0"
    cursor.execute(
        f'''
        SELECT id, name, code, symbol, asset_type, tags, builder_graph, validation_summary, optimization_summary, is_baseline, is_archived, created_at, last_modified
        FROM strategies
        {where_clause}
        ORDER BY is_baseline DESC, last_modified DESC
        LIMIT ?
        ''',
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "name": row[1],
            "code": row[2],
            "symbol": row[3],
            "asset_type": row[4],
            "tags": json.loads(row[5] or '[]'),
            "builder_graph": json.loads(row[6] or '{}'),
            "validation_summary": json.loads(row[7] or '{}'),
            "optimization_summary": json.loads(row[8] or '{}'),
            "is_baseline": bool(row[9]),
            "is_archived": bool(row[10]),
            "created_at": row[11],
            "last_modified": row[12],
        }
        for row in rows
    ]

def get_strategy(strategy_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT id, name, code, symbol, asset_type, tags, builder_graph, validation_summary, optimization_summary, is_baseline, is_archived, created_at, last_modified
        FROM strategies
        WHERE id = ?
        ''',
        (strategy_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "code": row[2],
        "symbol": row[3],
        "asset_type": row[4],
        "tags": json.loads(row[5] or '[]'),
        "builder_graph": json.loads(row[6] or '{}'),
        "validation_summary": json.loads(row[7] or '{}'),
        "optimization_summary": json.loads(row[8] or '{}'),
        "is_baseline": bool(row[9]),
        "is_archived": bool(row[10]),
        "created_at": row[11],
        "last_modified": row[12],
    }

def set_strategy_baseline(strategy_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE strategies SET is_baseline = 0")
    cursor.execute("UPDATE strategies SET is_baseline = 1, last_modified = CURRENT_TIMESTAMP WHERE id = ?", (strategy_id,))
    conn.commit()
    conn.close()
    return True

def archive_strategy(strategy_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE strategies SET is_archived = 1, is_baseline = 0, last_modified = CURRENT_TIMESTAMP WHERE id = ?", (strategy_id,))
    conn.commit()
    conn.close()
    return True

def restore_strategy(strategy_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE strategies SET is_archived = 0, last_modified = CURRENT_TIMESTAMP WHERE id = ?", (strategy_id,))
    conn.commit()
    conn.close()
    return True

def archive_strategies(strategy_ids: Iterable[int]):
    ids = [int(strategy_id) for strategy_id in strategy_ids]
    if not ids:
        return 0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in ids)
    cursor.execute(
        f"UPDATE strategies SET is_archived = 1, is_baseline = 0, last_modified = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
        ids,
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected

def restore_strategies(strategy_ids: Iterable[int]):
    ids = [int(strategy_id) for strategy_id in strategy_ids]
    if not ids:
        return 0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in ids)
    cursor.execute(
        f"UPDATE strategies SET is_archived = 0, last_modified = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
        ids,
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected

def permanently_delete_archived_strategies(strategy_ids: Iterable[int]):
    ids = [int(strategy_id) for strategy_id in strategy_ids]
    if not ids:
        return 0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in ids)
    cursor.execute(
        f"DELETE FROM strategies WHERE is_archived = 1 AND id IN ({placeholders})",
        ids,
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected

def duplicate_strategy(strategy_id: int):
    strategy = get_strategy(strategy_id)
    if not strategy:
        return None
    return save_strategy(
        name=f"{strategy['name']} Copy",
        code=strategy["code"],
        symbol=strategy.get("symbol", ""),
        asset_type=strategy.get("asset_type", "crypto"),
        tags=strategy.get("tags", []),
        builder_graph=strategy.get("builder_graph", {}),
        validation_summary=strategy.get("validation_summary", {}),
        optimization_summary=strategy.get("optimization_summary", {}),
        is_baseline=False,
    )

if __name__ == "__main__":
    init_db()
    print("SQLite database initialized successfully.")
