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
        api_keys TEXT, -- JSON credentials; plaintext legacy storage pending secure migration
        theme TEXT DEFAULT 'dark',
        paper_trading BOOLEAN DEFAULT 1,
        risk_live_trading_enabled BOOLEAN DEFAULT 0,
        risk_max_order_notional REAL DEFAULT 1000.0,
        risk_max_position_pct REAL DEFAULT 25.0,
        risk_max_daily_loss_pct REAL DEFAULT 3.0,
        risk_max_drawdown_pct REAL DEFAULT 10.0
    )
    ''')

    existing_settings_columns = {row[1] for row in cursor.execute("PRAGMA table_info(settings)").fetchall()}
    settings_column_migrations = {
        "risk_live_trading_enabled": "ALTER TABLE settings ADD COLUMN risk_live_trading_enabled BOOLEAN DEFAULT 0",
        "risk_max_order_notional": "ALTER TABLE settings ADD COLUMN risk_max_order_notional REAL DEFAULT 1000.0",
        "risk_max_position_pct": "ALTER TABLE settings ADD COLUMN risk_max_position_pct REAL DEFAULT 25.0",
        "risk_max_daily_loss_pct": "ALTER TABLE settings ADD COLUMN risk_max_daily_loss_pct REAL DEFAULT 3.0",
        "risk_max_drawdown_pct": "ALTER TABLE settings ADD COLUMN risk_max_drawdown_pct REAL DEFAULT 10.0",
    }
    for column, statement in settings_column_migrations.items():
        if column not in existing_settings_columns:
            cursor.execute(statement)

    # Persistent account equity baselines for loss/drawdown risk controls.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS risk_equity_state (
        broker_id TEXT NOT NULL,
        execution_mode TEXT NOT NULL,
        trading_day TEXT NOT NULL,
        day_start_equity REAL NOT NULL,
        peak_equity REAL NOT NULL,
        last_equity REAL NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (broker_id, execution_mode)
    )
    ''')

    # Persistent simulated brokerage account. A single JSON payload is used so
    # cash, positions, and marks are committed atomically.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS paper_account_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        state_json TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

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
        "requested_qty": "ALTER TABLE trades ADD COLUMN requested_qty REAL",
        "filled_qty": "ALTER TABLE trades ADD COLUMN filled_qty REAL DEFAULT 0",
        "filled_price": "ALTER TABLE trades ADD COLUMN filled_price REAL DEFAULT 0",
    }
    for column, statement in trade_column_migrations.items():
        if column not in existing_trade_columns:
            cursor.execute(statement)
    cursor.execute("UPDATE trades SET requested_qty = qty WHERE requested_qty IS NULL")

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
                   risk_live_trading_enabled, risk_max_order_notional, risk_max_position_pct,
                   risk_max_daily_loss_pct, risk_max_drawdown_pct
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
                "risk_max_daily_loss_pct": float(row[7] or 3.0),
                "risk_max_drawdown_pct": float(row[8] or 10.0),
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


def _preserve_legacy_api_keys(api_keys: dict | None, current_api_keys: dict | None) -> dict:
    """Never persist newly supplied credential material to SQLite.

    Masked placeholders preserve existing legacy values during migration.
    Empty values remove a legacy value. Any new non-masked secret must be
    stored by the credential provider instead of this settings table.
    """
    current = dict(current_api_keys or {})
    if api_keys is None:
        return current

    for key, value in api_keys.items():
        value = "" if value is None else str(value)
        if value == "********":
            continue
        if value == "":
            current.pop(key, None)
            continue
        if current.get(key) == value:
            continue
        raise ValueError(
            f"Refusing to persist credential '{key}' in plaintext SQLite. "
            "Use the secure credential store or environment variable."
        )
    return current


def update_settings(
    api_keys: dict = None,
    theme: str = None,
    paper_trading: bool = None,
    risk_live_trading_enabled: bool = None,
    risk_max_order_notional: float = None,
    risk_max_position_pct: float = None,
    risk_max_daily_loss_pct: float = None,
    risk_max_drawdown_pct: float = None,
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
    max_daily_loss_pct = float(risk_max_daily_loss_pct) if risk_max_daily_loss_pct is not None else current["risk_max_daily_loss_pct"]
    if not 0 < max_daily_loss_pct <= 100:
        raise ValueError("risk_max_daily_loss_pct must be between 0 and 100")
    max_drawdown_pct = float(risk_max_drawdown_pct) if risk_max_drawdown_pct is not None else current["risk_max_drawdown_pct"]
    if not 0 < max_drawdown_pct <= 100:
        raise ValueError("risk_max_drawdown_pct must be between 0 and 100")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE settings
        SET api_keys = ?, theme = ?, paper_trading = ?,
            risk_live_trading_enabled = ?, risk_max_order_notional = ?, risk_max_position_pct = ?,
            risk_max_daily_loss_pct = ?, risk_max_drawdown_pct = ?
        WHERE id = 1
    """, (
        json.dumps(_preserve_legacy_api_keys(api_keys, current["api_keys"])),
        theme if theme is not None else current["theme"],
        int(paper_trading) if paper_trading is not None else int(current["paper_trading"]),
        int(risk_live_trading_enabled) if risk_live_trading_enabled is not None else int(current["risk_live_trading_enabled"]),
        max_notional,
        max_position_pct,
        max_daily_loss_pct,
        max_drawdown_pct,
    ))
    conn.commit()
    conn.close()
    return True


def get_paper_account_state():
    """Return the persisted paper account payload, or None when not initialized."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT state_json FROM paper_account_state WHERE id = 1")
        row = cursor.fetchone()
    except sqlite3.Error:
        row = None
    finally:
        conn.close()
    if not row:
        return None
    try:
        state = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return None
    return state if isinstance(state, dict) else None


def save_paper_account_state(state: dict) -> None:
    """Atomically persist the complete simulated brokerage account."""
    payload = json.dumps(state, sort_keys=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO paper_account_state (id, state_json, updated_at)
        VALUES (1, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            state_json = excluded.state_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (payload,),
    )
    conn.commit()
    conn.close()


def clear_risk_equity_state(broker_id: str, execution_mode: str) -> None:
    """Clear a risk baseline when its underlying simulated account is reset."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM risk_equity_state WHERE broker_id = ? AND execution_mode = ?",
        (broker_id, execution_mode),
    )
    conn.commit()
    conn.close()


def update_risk_equity_state(
    broker_id: str,
    execution_mode: str,
    equity: float,
    trading_day: str | None = None,
):
    """Persist daily-start and peak equity so risk limits survive restarts."""
    equity = float(equity)
    if equity <= 0:
        raise ValueError("equity must be positive")
    trading_day = trading_day or datetime.now().date().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT trading_day, day_start_equity, peak_equity
        FROM risk_equity_state
        WHERE broker_id = ? AND execution_mode = ?
        """,
        (broker_id, execution_mode),
    )
    row = cursor.fetchone()

    if row is None:
        day_start_equity = equity
        peak_equity = equity
        cursor.execute(
            """
            INSERT INTO risk_equity_state
                (broker_id, execution_mode, trading_day, day_start_equity, peak_equity, last_equity)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (broker_id, execution_mode, trading_day, equity, equity, equity),
        )
    else:
        stored_day, stored_day_start, stored_peak = row
        day_start_equity = equity if stored_day != trading_day else float(stored_day_start)
        peak_equity = max(float(stored_peak), equity)
        cursor.execute(
            """
            UPDATE risk_equity_state
            SET trading_day = ?, day_start_equity = ?, peak_equity = ?,
                last_equity = ?, updated_at = CURRENT_TIMESTAMP
            WHERE broker_id = ? AND execution_mode = ?
            """,
            (trading_day, day_start_equity, peak_equity, equity, broker_id, execution_mode),
        )

    conn.commit()
    conn.close()
    return {
        "broker_id": broker_id,
        "execution_mode": execution_mode,
        "trading_day": trading_day,
        "day_start_equity": day_start_equity,
        "peak_equity": peak_equity,
        "last_equity": equity,
    }


def get_risk_equity_state(broker_id: str, execution_mode: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT trading_day, day_start_equity, peak_equity, last_equity, updated_at
        FROM risk_equity_state
        WHERE broker_id = ? AND execution_mode = ?
        """,
        (broker_id, execution_mode),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "broker_id": broker_id,
        "execution_mode": execution_mode,
        "trading_day": row[0],
        "day_start_equity": float(row[1]),
        "peak_equity": float(row[2]),
        "last_equity": float(row[3]),
        "updated_at": row[4],
    }


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
    requested_qty: float | None = None,
    filled_qty: float | None = None,
    filled_price: float | None = None,
):
    requested_qty = float(qty if requested_qty is None else requested_qty)
    filled_qty = float(qty if filled_qty is None and order_status == "filled" else (filled_qty or 0.0))
    filled_price = float(price if filled_price is None and filled_qty > 0 else (filled_price or 0.0))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO trades (
            symbol, side, qty, price, broker_id, execution_mode, is_paper,
            order_status, order_type, broker_order_id, is_test, metadata,
            requested_qty, filled_qty, filled_price
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol, side, qty, price, broker_id, execution_mode, int(is_paper),
            order_status, order_type, broker_order_id, int(is_test),
            json.dumps(metadata or {}), requested_qty, filled_qty, filled_price,
        ),
    )
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
        SELECT id, symbol, side, qty, price, broker_id, execution_mode, timestamp,
               is_paper, order_status, order_type, broker_order_id, is_test, metadata,
               requested_qty, filled_qty, filled_price
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
            "metadata": json.loads(r[13] or "{}"),
            "requested_qty": float(r[14] if r[14] is not None else r[3]),
            "filled_qty": float(r[15] or 0),
            "filled_price": float(r[16] or 0),
        }
        for r in rows
    ]


def get_trade_by_id(trade_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, symbol, side, qty, price, broker_id, execution_mode, timestamp,
               is_paper, order_status, order_type, broker_order_id, is_test, metadata,
               requested_qty, filled_qty, filled_price
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
        "metadata": json.loads(row[13] or "{}"),
        "requested_qty": float(row[14] if row[14] is not None else row[3]),
        "filled_qty": float(row[15] or 0),
        "filled_price": float(row[16] or 0),
    }


def update_trade_order_state(
    trade_id: int,
    order_status: str,
    broker_order_id: str | None = None,
    metadata: dict | None = None,
    filled_qty: float | None = None,
    filled_price: float | None = None,
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE trades
        SET order_status = ?,
            broker_order_id = COALESCE(?, broker_order_id),
            metadata = ?,
            filled_qty = COALESCE(?, filled_qty),
            filled_price = COALESCE(?, filled_price),
            timestamp = timestamp
        WHERE id = ?
        """,
        (
            order_status,
            broker_order_id,
            json.dumps(metadata or {}),
            filled_qty,
            filled_price,
            trade_id,
        ),
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
