"""Business logic layer for Smart Task Manager.

Pure Python only: no Streamlit and no database imports here. That keeps every
function easy to unit test with plain dictionaries.

A "task" is a dict shaped like a row of the `tasks` table, for example:
    {"task_id": 1, "title": "Finish report", "priority": "High",
     "status": "Pending", "due_date": "2026-11-05", ...}
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping

Task = Mapping[str, object]

PRIORITIES = ("High", "Medium", "Low")
STATUSES = ("Pending", "In Progress", "Completed")
CATEGORIES = ("Academic", "Personal", "Project", "Work", "Health", "Other")

MAX_TITLE_LENGTH = 100
DUE_SOON_DAYS = 3  # "approaching deadline" window used for highlighting
UPCOMING_DAYS = 7  # window used by the Upcoming & Overdue page


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_task(
    title: object,
    priority: object,
    due_date: object,
    status: str = "Pending",
) -> list[str]:
    """Return a list of error messages. An empty list means the input is valid.

    Past due dates are allowed on purpose, so overdue tasks can exist.
    """
    errors: list[str] = []

    if not isinstance(title, str) or not title.strip():
        errors.append("Title cannot be empty.")
    elif len(title.strip()) > MAX_TITLE_LENGTH:
        errors.append(f"Title must be at most {MAX_TITLE_LENGTH} characters.")

    if priority not in PRIORITIES:
        errors.append("Priority must be High, Medium or Low.")

    if status not in STATUSES:
        errors.append("Status must be Pending, In Progress or Completed.")

    # datetime is a subclass of date, so rule it out explicitly.
    if not isinstance(due_date, date) or isinstance(due_date, datetime):
        errors.append("Please choose a valid due date.")

    return errors


# --------------------------------------------------------------------------
# Dates and deadlines
# --------------------------------------------------------------------------
def parse_due_date(value: object) -> date | None:
    """Convert a stored ISO string (YYYY-MM-DD) to a date. Bad or missing -> None."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def is_completed(task: Task) -> bool:
    return task.get("status") == "Completed"


def days_until_due(task: Task, today: date | None = None) -> int | None:
    """Days from today to the deadline (negative = already past). None if no date."""
    due = parse_due_date(task.get("due_date"))
    if due is None:
        return None
    return (due - (today or date.today())).days


def is_overdue(task: Task, today: date | None = None) -> bool:
    """Overdue = NOT completed and the due date is before today.

    A task due today is not overdue yet, and a completed task never is.
    """
    if is_completed(task):
        return False
    days = days_until_due(task, today)
    return days is not None and days < 0


def is_due_soon(
    task: Task, today: date | None = None, days: int = DUE_SOON_DAYS
) -> bool:
    """Incomplete task whose deadline is today or within the next `days` days."""
    if is_completed(task):
        return False
    left = days_until_due(task, today)
    return left is not None and 0 <= left <= days


def deadline_status(task: Task, today: date | None = None) -> str:
    """One of: completed, none, overdue, today, soon, later."""
    if is_completed(task):
        return "completed"
    left = days_until_due(task, today)
    if left is None:
        return "none"
    if left < 0:
        return "overdue"
    if left == 0:
        return "today"
    if left <= DUE_SOON_DAYS:
        return "soon"
    return "later"


def deadline_label(task: Task, today: date | None = None) -> str:
    """Short human-readable text for the deadline."""
    state = deadline_status(task, today)
    left = days_until_due(task, today)
    if state == "completed":
        return "Completed"
    if state == "none" or left is None:
        return "No due date"
    if state == "overdue":
        n = -left
        return f"Overdue by {n} day{'s' if n != 1 else ''}"
    if state == "today":
        return "Due today"
    return f"Due in {left} day{'s' if left != 1 else ''}"


# --------------------------------------------------------------------------
# Dashboard statistics
# --------------------------------------------------------------------------
def calculate_stats(tasks: Iterable[Task], today: date | None = None) -> dict:
    """Numbers for the dashboard.

    The three groups never overlap, so completed + pending + overdue == total:
      completed -> status is Completed
      overdue   -> not completed and past its due date
      pending   -> not completed and not overdue (Pending or In Progress)
    """
    tasks = list(tasks)
    total = len(tasks)
    completed = sum(1 for t in tasks if is_completed(t))
    overdue = sum(1 for t in tasks if is_overdue(t, today))
    pending = total - completed - overdue
    percentage = round(completed / total * 100, 1) if total else 0.0
    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "overdue": overdue,
        "completion_percentage": percentage,
    }


# --------------------------------------------------------------------------
# Search, filter, sort
# --------------------------------------------------------------------------
def filter_tasks(
    tasks: Iterable[Task],
    search: str = "",
    priority: str = "All",
    status: str = "All",
) -> list[Task]:
    """Case-insensitive title search plus optional priority and status filters."""
    needle = (search or "").strip().lower()
    result = []
    for task in tasks:
        if needle and needle not in str(task.get("title", "")).lower():
            continue
        if priority != "All" and task.get("priority") != priority:
            continue
        if status != "All" and task.get("status") != status:
            continue
        result.append(task)
    return result


def sort_by_due_date(tasks: Iterable[Task], descending: bool = False) -> list[Task]:
    """Sort by due date. Tasks without a valid date always go to the end."""
    dated, undated = [], []
    for task in tasks:
        (dated if parse_due_date(task.get("due_date")) else undated).append(task)
    dated.sort(key=lambda t: parse_due_date(t.get("due_date")), reverse=descending)
    return dated + undated


def group_by_deadline(
    tasks: Iterable[Task], today: date | None = None, window: int = UPCOMING_DAYS
) -> dict[str, list[Task]]:
    """Split incomplete tasks into overdue / due_soon (within `window` days) / later."""
    today = today or date.today()
    groups: dict[str, list[Task]] = {"overdue": [], "due_soon": [], "later": []}
    for task in tasks:
        if is_completed(task):
            continue
        left = days_until_due(task, today)
        if left is None:
            groups["later"].append(task)
        elif left < 0:
            groups["overdue"].append(task)
        elif left <= window:
            groups["due_soon"].append(task)
        else:
            groups["later"].append(task)
    return {name: sort_by_due_date(items) for name, items in groups.items()}
