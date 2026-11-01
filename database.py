"""Data layer for Smart Task Manager (SQLite).

Every function takes an optional `db_path`, so tests can use a temporary
database instead of the real tasks.db. All SQL uses ? placeholders
(parameterized queries) - never string concatenation.
"""

import os
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

# tasks.db sits next to this file. TASK_DB_PATH lets tests point somewhere else.
DB_PATH = Path(os.environ.get("TASK_DB_PATH") or Path(__file__).with_name("tasks.db"))

VALID_PRIORITIES = {"High", "Medium", "Low"}
VALID_STATUSES = {"Pending", "In Progress", "Completed"}


def init_db(db_path: str | Path = DB_PATH) -> None:
    """Create the tasks table if it does not already exist (never wipes data)."""
    with closing(sqlite3.connect(db_path)) as connection:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                    description TEXT,
                    category TEXT,
                    priority TEXT NOT NULL
                        CHECK (priority IN ('High', 'Medium', 'Low')),
                    status TEXT NOT NULL
                        CHECK (status IN ('Pending', 'In Progress', 'Completed')),
                    due_date TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )


def _check_fields(title: str, priority: str, status: str, due_date: str | None) -> None:
    """Raise ValueError if any field is invalid (shared by add and update)."""
    if not title.strip():
        raise ValueError("Title cannot be empty.")
    if priority not in VALID_PRIORITIES:
        raise ValueError("Priority must be High, Medium, or Low.")
    if status not in VALID_STATUSES:
        raise ValueError("Status must be Pending, In Progress, or Completed.")
    if due_date is not None:
        try:
            parsed_due_date = date.fromisoformat(due_date)
        except ValueError as error:
            raise ValueError("Due date must use YYYY-MM-DD format.") from error
        if parsed_due_date.isoformat() != due_date:
            raise ValueError("Due date must use YYYY-MM-DD format.")


def add_task(
    title: str,
    description: str = "",
    category: str = "",
    priority: str = "Medium",
    status: str = "Pending",
    due_date: str | None = None,
    db_path: str | Path = DB_PATH,
) -> int:
    """Insert a task and return its generated task_id."""
    _check_fields(title, priority, status, due_date)

    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    with closing(sqlite3.connect(db_path)) as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO tasks (
                    title, description, category, priority, status, due_date, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    description,
                    category,
                    priority,
                    status,
                    due_date,
                    created_at,
                ),
            )
            return cursor.lastrowid


def get_all_tasks(db_path: str | Path = DB_PATH) -> list[dict]:
    """Return every task as a dict, oldest first."""
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row  # rows behave like dicts
        rows = connection.execute("SELECT * FROM tasks ORDER BY task_id").fetchall()
    return [dict(row) for row in rows]


def get_task(task_id: int, db_path: str | Path = DB_PATH) -> dict | None:
    """Return one task as a dict, or None if the id does not exist."""
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
    return dict(row) if row else None


def update_task(
    task_id: int,
    title: str,
    description: str,
    category: str,
    priority: str,
    status: str,
    due_date: str | None,
    db_path: str | Path = DB_PATH,
) -> bool:
    """Edit a task. Returns True if a row was changed, False if the id is unknown."""
    _check_fields(title, priority, status, due_date)
    with closing(sqlite3.connect(db_path)) as connection:
        with connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET title = ?, description = ?, category = ?,
                    priority = ?, status = ?, due_date = ?
                WHERE task_id = ?
                """,
                (title.strip(), description, category, priority, status, due_date, task_id),
            )
            return cursor.rowcount > 0


def update_status(
    task_id: int, status: str, db_path: str | Path = DB_PATH
) -> bool:
    """Change only the status of a task. Returns True if a row was changed."""
    if status not in VALID_STATUSES:
        raise ValueError("Status must be Pending, In Progress, or Completed.")
    with closing(sqlite3.connect(db_path)) as connection:
        with connection:
            cursor = connection.execute(
                "UPDATE tasks SET status = ? WHERE task_id = ?", (status, task_id)
            )
            return cursor.rowcount > 0


def delete_task(task_id: int, db_path: str | Path = DB_PATH) -> bool:
    """Delete a task. Returns True if a row was removed."""
    with closing(sqlite3.connect(db_path)) as connection:
        with connection:
            cursor = connection.execute(
                "DELETE FROM tasks WHERE task_id = ?", (task_id,)
            )
            return cursor.rowcount > 0
