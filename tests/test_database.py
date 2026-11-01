import sqlite3

import pytest

from database import add_task, init_db


def test_init_db_preserves_existing_tasks(tmp_path):
    db_path = tmp_path / "tasks.db"
    init_db(db_path)
    task_id = add_task("Existing task", db_path=db_path)

    init_db(db_path)

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT task_id, title FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    assert row == (task_id, "Existing task")


def test_add_task_inserts_task_and_returns_id(tmp_path):
    db_path = tmp_path / "tasks.db"
    init_db(db_path)

    task_id = add_task(
        "Plan release",
        "Prepare release notes",
        "Work",
        "High",
        "In Progress",
        "2026-11-05",
        db_path,
    )

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT title, description, category, priority, status, due_date, created_at
            FROM tasks WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
    assert row[:6] == (
        "Plan release",
        "Prepare release notes",
        "Work",
        "High",
        "In Progress",
        "2026-11-05",
    )
    assert row[6]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "   "),
        ("priority", "Urgent"),
        ("status", "Blocked"),
        ("due_date", "11/05/2026"),
    ],
)
def test_add_task_rejects_invalid_values(tmp_path, field, value):
    db_path = tmp_path / "tasks.db"
    init_db(db_path)
    arguments = {"title": "Task", field: value}

    with pytest.raises(ValueError):
        add_task(**arguments, db_path=db_path)


# ---------------------------------------------------------------------------
# Read / update / delete
# ---------------------------------------------------------------------------
from database import (  # noqa: E402  (grouped here to keep the original tests untouched)
    delete_task,
    get_all_tasks,
    get_task,
    update_status,
    update_task,
)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "tasks.db"
    init_db(path)
    return path


def test_get_all_tasks_returns_saved_tasks_as_dicts(db_path):
    add_task("First", priority="High", due_date="2026-11-05", db_path=db_path)
    add_task("Second", priority="Low", due_date="2026-11-06", db_path=db_path)

    tasks = get_all_tasks(db_path)

    assert [t["title"] for t in tasks] == ["First", "Second"]
    assert tasks[0]["priority"] == "High"
    assert tasks[0]["status"] == "Pending"


def test_get_all_tasks_on_empty_database(db_path):
    assert get_all_tasks(db_path) == []


def test_get_task_by_id_and_unknown_id(db_path):
    task_id = add_task("Find me", db_path=db_path)
    assert get_task(task_id, db_path)["title"] == "Find me"
    assert get_task(9999, db_path) is None


def test_update_task_saves_changes(db_path):
    task_id = add_task("Old title", priority="Low", due_date="2026-11-05", db_path=db_path)

    changed = update_task(
        task_id, "New title", "details", "Project", "High", "In Progress", "2026-12-01",
        db_path=db_path,
    )

    assert changed is True
    task = get_task(task_id, db_path)
    assert task["title"] == "New title"
    assert task["description"] == "details"
    assert task["priority"] == "High"
    assert task["status"] == "In Progress"
    assert task["due_date"] == "2026-12-01"


def test_update_task_rejects_invalid_values(db_path):
    task_id = add_task("Task", db_path=db_path)
    with pytest.raises(ValueError):
        update_task(task_id, "  ", "", "", "High", "Pending", "2026-11-05", db_path=db_path)
    with pytest.raises(ValueError):
        update_task(task_id, "Task", "", "", "Urgent", "Pending", "2026-11-05", db_path=db_path)
    assert get_task(task_id, db_path)["title"] == "Task"  # unchanged


def test_update_task_unknown_id_returns_false(db_path):
    assert update_task(9999, "T", "", "", "High", "Pending", "2026-11-05", db_path=db_path) is False


def test_update_status_marks_completed(db_path):
    task_id = add_task("Finish me", db_path=db_path)
    assert update_status(task_id, "Completed", db_path) is True
    assert get_task(task_id, db_path)["status"] == "Completed"


def test_update_status_rejects_invalid_status(db_path):
    task_id = add_task("Task", db_path=db_path)
    with pytest.raises(ValueError):
        update_status(task_id, "Blocked", db_path)


def test_delete_task_removes_only_that_task(db_path):
    keep = add_task("Keep", db_path=db_path)
    remove = add_task("Remove", db_path=db_path)

    assert delete_task(remove, db_path) is True

    assert [t["task_id"] for t in get_all_tasks(db_path)] == [keep]
    assert delete_task(remove, db_path) is False  # already gone


def test_tasks_survive_a_restart(db_path):
    """Simulates closing and reopening the app: init_db again, data still there."""
    add_task("Persistent", db_path=db_path)
    init_db(db_path)
    assert [t["title"] for t in get_all_tasks(db_path)] == ["Persistent"]


def test_sql_injection_text_is_stored_as_plain_text(db_path):
    nasty = "x'); DROP TABLE tasks;--"
    add_task(nasty, db_path=db_path)
    assert get_all_tasks(db_path)[0]["title"] == nasty


def test_database_itself_rejects_bad_priority(db_path):
    """The CHECK constraint is a second line of defence behind the Python checks."""
    with sqlite3.connect(db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO tasks (title, priority, status, created_at) "
                "VALUES ('x', 'Urgent', 'Pending', 'now')"
            )
