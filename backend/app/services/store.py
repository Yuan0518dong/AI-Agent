import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

# Keep this hook when migrating goal/task storage; material data lives in material_store.
from backend.app.services import database, material_store

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "ai_agent.db"
DB_PATH = DEFAULT_DB_PATH


def set_db_path(path: str | Path | None) -> None:
    global DB_PATH
    database.set_sqlite_test_mode(path is not None)
    DB_PATH = Path(path) if path else DEFAULT_DB_PATH
    material_store.set_db_path(DB_PATH)
    init_db()


def get_connection():
    if database.using_postgres():
        return database.connect()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.parent != DATA_DIR:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_connection():
    conn = get_connection()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    if database.using_postgres():
        database.ensure_postgres_schema_ready()
        return
    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                level TEXT NOT NULL,
                deadline TEXT NOT NULL,
                daily_minutes INTEGER NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                date TEXT NOT NULL,
                priority TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS checkins (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                account_type TEXT NOT NULL DEFAULT 'registered',
                password_algorithm TEXT NOT NULL DEFAULT 'pbkdf2_sha256',
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_auth_sessions_token_hash
            ON auth_sessions(token_hash);

            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id
            ON auth_sessions(user_id);

            CREATE TABLE IF NOT EXISTS rate_limit_counters (
                scope TEXT NOT NULL,
                identifier_hash TEXT NOT NULL,
                window_start TEXT NOT NULL,
                count INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (scope, identifier_hash, window_start)
            );

            CREATE TABLE IF NOT EXISTS model_usage_counters (
                scope TEXT NOT NULL,
                owner_hash TEXT NOT NULL,
                period_start TEXT NOT NULL,
                units INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (scope, owner_hash, period_start)
            );

            CREATE TABLE IF NOT EXISTS agent_action_logs (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                goal_id TEXT,
                action_type TEXT NOT NULL,
                observation TEXT NOT NULL,
                decision TEXT NOT NULL,
                proposed_payload TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS agent_runs (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                goal_id TEXT,
                trigger TEXT NOT NULL,
                objective TEXT NOT NULL DEFAULT '',
                decision_mode TEXT NOT NULL DEFAULT 'rule-based',
                max_steps INTEGER NOT NULL DEFAULT 4,
                current_step INTEGER NOT NULL DEFAULT 0,
                context_snapshot TEXT NOT NULL,
                decision_snapshot TEXT NOT NULL,
                feedback_summary TEXT NOT NULL,
                status TEXT NOT NULL,
                stop_reason TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS agent_run_steps (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                context_snapshot TEXT NOT NULL,
                decision_snapshot TEXT NOT NULL,
                action_snapshot TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                tool_input TEXT NOT NULL,
                tool_output TEXT NOT NULL,
                action_log_id TEXT,
                status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(run_id, step_index),
                FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (action_log_id) REFERENCES agent_action_logs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS agent_drafts (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                goal_id TEXT,
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                draft_type TEXT NOT NULL CHECK(draft_type IN ('review', 'task')),
                payload TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('proposed', 'confirmed', 'applied', 'rejected')),
                idempotency_key TEXT NOT NULL UNIQUE,
                applied_entity_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                applied_at TEXT,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE SET NULL,
                FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (step_id) REFERENCES agent_run_steps(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_agent_drafts_owner_created
            ON agent_drafts(user_id, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_agent_drafts_owner_goal_created
            ON agent_drafts(user_id, goal_id, created_at DESC);
            """
        )
        _ensure_columns(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                goal_id TEXT,
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS material_summaries (
                material_id TEXT PRIMARY KEY,
                overview TEXT NOT NULL,
                key_points TEXT NOT NULL,
                difficulties TEXT NOT NULL,
                study_order TEXT NOT NULL,
                action_items TEXT NOT NULL,
                ai_mode TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS flashcards (
                id TEXT PRIMARY KEY,
                material_id TEXT NOT NULL,
                front TEXT NOT NULL,
                back TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_questions (
                id TEXT PRIMARY KEY,
                material_id TEXT NOT NULL,
                question TEXT NOT NULL,
                type TEXT NOT NULL,
                options TEXT NOT NULL,
                answer TEXT NOT NULL,
                explanation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id TEXT PRIMARY KEY,
                quiz_id TEXT NOT NULL,
                material_id TEXT NOT NULL,
                user_answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                score INTEGER NOT NULL,
                feedback TEXT NOT NULL,
                suggestion TEXT NOT NULL,
                mode TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (quiz_id) REFERENCES quiz_questions(id) ON DELETE CASCADE,
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
            )
            """
        )

    # Keep the material schema hook aligned for fresh local databases.
    material_store.init_db()


def reset() -> None:
    init_db()
    with db_connection() as conn:
        conn.execute("DELETE FROM model_usage_counters")
        conn.execute("DELETE FROM rate_limit_counters")
        conn.execute("DELETE FROM auth_sessions")
        conn.execute("DELETE FROM agent_drafts")
        conn.execute("DELETE FROM agent_run_steps")
        conn.execute("DELETE FROM agent_runs")
        conn.execute("DELETE FROM agent_action_logs")
        conn.execute("DELETE FROM checkins")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM goals")
        conn.execute("DELETE FROM users")

    # Smoke tests call store.reset(), so material SQLite test data must be cleared here too.
    material_store.clear_material_data()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def list_goals(user_id: str | None = None) -> list[dict]:
    init_db()
    with db_connection() as conn:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM goals WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
    return [_goal_from_row(row) for row in rows]


def create_goal(goal: dict) -> dict:
    init_db()
    goal_for_db = {"user_id": None, **goal}
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO goals (
                id, user_id, name, subject, level, deadline, daily_minutes, notes, created_at, updated_at
            ) VALUES (
                :id, :user_id, :name, :subject, :level, :deadline, :daily_minutes, :notes, :created_at, :updated_at
            )
            """,
            goal_for_db,
        )
    return goal


def create_user(user: dict) -> dict:
    init_db()
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (
                id, name, email, password_hash, password_salt, account_type,
                password_algorithm, expires_at, created_at, updated_at
            ) VALUES (
                :id, :name, :email, :password_hash, :password_salt, :account_type,
                :password_algorithm, :expires_at, :created_at, :updated_at
            )
            """,
            user,
        )
    return user


def get_user_by_email(email: str) -> dict | None:
    init_db()
    with db_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return _user_from_row(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    init_db()
    with db_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_from_row(row) if row else None


def update_user_password(
    user_id: str,
    password_hash: str,
    password_salt: str,
    password_algorithm: str,
    updated_at: str,
) -> dict | None:
    init_db()
    with db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE users
            SET password_hash = ?, password_salt = ?, password_algorithm = ?, updated_at = ?
            WHERE id = ?
            """,
            (password_hash, password_salt, password_algorithm, updated_at, user_id),
        )
        if cursor.rowcount == 0:
            return None
    return get_user_by_id(user_id)


def create_auth_session(session: dict) -> dict:
    init_db()
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_sessions (id, user_id, token_hash, expires_at, revoked_at, created_at)
            VALUES (:id, :user_id, :token_hash, :expires_at, :revoked_at, :created_at)
            """,
            session,
        )
    return session


def get_active_user_by_session_hash(token_hash: str, now: str) -> dict | None:
    init_db()
    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT users.*
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ?
              AND auth_sessions.revoked_at IS NULL
              AND auth_sessions.expires_at > ?
              AND (users.expires_at IS NULL OR users.expires_at > ?)
            """,
            (token_hash, now, now),
        ).fetchone()
    return _user_from_row(row) if row else None


def revoke_auth_session(token_hash: str, revoked_at: str) -> bool:
    init_db()
    with db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = ?
            WHERE token_hash = ? AND revoked_at IS NULL
            """,
            (revoked_at, token_hash),
        )
    return cursor.rowcount > 0


def increment_rate_limit(
    scope: str,
    identifier_hash: str,
    window_start: str,
    limit: int,
    updated_at: str,
) -> int | None:
    """Atomically reserve one request slot, returning the new count or None when exhausted."""
    init_db()
    with db_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO rate_limit_counters (scope, identifier_hash, window_start, count, updated_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(scope, identifier_hash, window_start) DO UPDATE SET
                count = rate_limit_counters.count + 1,
                updated_at = excluded.updated_at
            WHERE rate_limit_counters.count < ?
            RETURNING count
            """,
            (scope, identifier_hash, window_start, updated_at, limit),
        ).fetchone()
    return int(row["count"]) if row else None


def increment_model_usage(
    scope: str,
    owner_hash: str,
    period_start: str,
    units: int,
    limit: int,
    updated_at: str,
) -> int | None:
    """Atomically reserve model usage units, returning the new total or None when exhausted."""
    init_db()
    with db_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO model_usage_counters (scope, owner_hash, period_start, units, updated_at)
            SELECT ?, ?, ?, ?, ?
            WHERE ? <= ?
            ON CONFLICT(scope, owner_hash, period_start) DO UPDATE SET
                units = model_usage_counters.units + excluded.units,
                updated_at = excluded.updated_at
            WHERE model_usage_counters.units + excluded.units <= ?
            RETURNING units
            """,
            (scope, owner_hash, period_start, units, updated_at, units, limit, limit),
        ).fetchone()
    return int(row["units"]) if row else None


class UsageLimitExceeded(Exception):
    pass


def reserve_model_usage_limits(
    reservations: list[tuple[str, str, str, int, int]],
    updated_at: str,
) -> bool:
    """Reserve all model quotas in one transaction or roll every reservation back."""
    init_db()
    try:
        with db_connection() as conn:
            for scope, owner_hash, period_start, units, limit in reservations:
                row = conn.execute(
                    """
                    INSERT INTO model_usage_counters (scope, owner_hash, period_start, units, updated_at)
                    SELECT ?, ?, ?, ?, ?
                    WHERE ? <= ?
                    ON CONFLICT(scope, owner_hash, period_start) DO UPDATE SET
                        units = model_usage_counters.units + excluded.units,
                        updated_at = excluded.updated_at
                    WHERE model_usage_counters.units + excluded.units <= ?
                    RETURNING units
                    """,
                    (scope, owner_hash, period_start, units, updated_at, units, limit, limit),
                ).fetchone()
                if not row:
                    raise UsageLimitExceeded(scope)
    except UsageLimitExceeded:
        return False
    return True


def get_goal(goal_id: str, user_id: str | None = None) -> dict | None:
    init_db()
    with db_connection() as conn:
        if user_id:
            row = conn.execute(
                "SELECT * FROM goals WHERE id = ? AND user_id = ?",
                (goal_id, user_id),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    return _goal_from_row(row) if row else None


def update_goal(goal_id: str, changes: dict, user_id: str | None = None) -> dict | None:
    if not changes:
        return get_goal(goal_id, user_id)

    allowed_fields = {"name", "subject", "level", "deadline", "daily_minutes", "notes", "updated_at"}
    assignments = []
    values = []
    for key, value in changes.items():
        if key not in allowed_fields:
            continue
        assignments.append(f"{key} = ?")
        values.append(value)

    if not assignments:
        return get_goal(goal_id, user_id)

    values.append(goal_id)
    if user_id:
        values.append(user_id)
    init_db()
    with db_connection() as conn:
        cursor = conn.execute(
            f"UPDATE goals SET {', '.join(assignments)} WHERE id = ?"
            + (" AND user_id = ?" if user_id else ""),
            values,
        )
        if cursor.rowcount == 0:
            return None
    return get_goal(goal_id, user_id)


def delete_goal(goal_id: str, user_id: str | None = None) -> bool:
    init_db()
    with db_connection() as conn:
        if user_id:
            cursor = conn.execute(
                "DELETE FROM goals WHERE id = ? AND user_id = ?",
                (goal_id, user_id),
            )
        else:
            cursor = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    return cursor.rowcount > 0


def list_goal_tasks(goal_id: str) -> list[dict]:
    init_db()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE goal_id = ? ORDER BY date ASC, created_at ASC",
            (goal_id,),
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def list_tasks_by_date(target_date: str, user_id: str | None = None) -> list[dict]:
    init_db()
    with db_connection() as conn:
        if user_id:
            rows = conn.execute(
                """
                SELECT tasks.* FROM tasks
                JOIN goals ON goals.id = tasks.goal_id
                WHERE tasks.date = ? AND goals.user_id = ?
                ORDER BY tasks.created_at ASC
                """,
                (target_date, user_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE date = ? ORDER BY created_at ASC",
                (target_date,),
            ).fetchall()
    return [_task_from_row(row) for row in rows]


def create_task(task: dict) -> dict:
    init_db()
    task_for_db = {**task, "done": int(task["done"])}
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                id, goal_id, title, detail, date, priority, done, completed_at, created_at, updated_at
            ) VALUES (
                :id, :goal_id, :title, :detail, :date, :priority, :done, :completed_at, :created_at, :updated_at
            )
            """,
            task_for_db,
        )
    return task


def get_task(task_id: str) -> dict | None:
    init_db()
    with db_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_from_row(row) if row else None


def delete_tasks_for_goal(goal_id: str) -> None:
    init_db()
    with db_connection() as conn:
        conn.execute("DELETE FROM tasks WHERE goal_id = ?", (goal_id,))


def set_task_checkin(task_id: str, done: bool) -> dict | None:
    task = get_task(task_id)
    if not task:
        return None

    now = now_iso()
    completed_at = now if done else None
    init_db()
    with db_connection() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET done = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (int(done), completed_at, now, task_id),
        )
        conn.execute(
            """
            INSERT INTO checkins (
                id, goal_id, task_id, date, status, checked_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                make_id("checkin"),
                task["goal_id"],
                task_id,
                today_iso(),
                "completed" if done else "canceled",
                now,
            ),
        )
    return get_task(task_id)


def goal_exists(goal_id: str, user_id: str | None = None) -> bool:
    return get_goal(goal_id, user_id) is not None


def _ensure_columns(conn: sqlite3.Connection) -> None:
    goal_columns = _column_names(conn, "goals")
    if "user_id" not in goal_columns:
        conn.execute("ALTER TABLE goals ADD COLUMN user_id TEXT")

    user_columns = _column_names(conn, "users")
    user_defaults = {
        "account_type": "'registered'",
        "password_algorithm": "'pbkdf2_sha256'",
        "expires_at": None,
    }
    for column, default in user_defaults.items():
        if column in user_columns:
            continue
        if default is None:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
        else:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}")

    agent_run_columns = _column_names(conn, "agent_runs")
    agent_run_defaults = {
        "objective": "''",
        "decision_mode": "'rule-based'",
        "max_steps": "4",
        "current_step": "0",
        "stop_reason": "''",
        "error": "''",
    }
    integer_columns = {"max_steps", "current_step"}
    for column, default in agent_run_defaults.items():
        if column not in agent_run_columns:
            column_type = "INTEGER" if column in integer_columns else "TEXT"
            conn.execute(
                f"ALTER TABLE agent_runs ADD COLUMN {column} {column_type} NOT NULL DEFAULT {default}"
            )


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _goal_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "subject": row["subject"],
        "level": row["level"],
        "deadline": row["deadline"],
        "daily_minutes": row["daily_minutes"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _task_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "goal_id": row["goal_id"],
        "title": row["title"],
        "detail": row["detail"],
        "date": row["date"],
        "priority": row["priority"],
        "done": bool(row["done"]),
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _user_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "password_hash": row["password_hash"],
        "password_salt": row["password_salt"],
        "account_type": row["account_type"],
        "password_algorithm": row["password_algorithm"],
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
