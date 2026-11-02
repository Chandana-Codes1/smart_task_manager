"""Collaborative Planning data layer (SQLite).

Adds users, follows, plans, plan members and invitations ON TOP of the existing
`tasks` table. Nothing here drops or recreates existing data.

Rules enforced here (not only in the UI):
  * passwords are stored as salted PBKDF2-SHA256 hashes, never as plain text
  * nobody can follow themselves, and a follow can only exist once
  * you can invite someone to a plan ONLY if you already follow them
  * only one pending invitation per (plan, person)
  * only plan members can see/add plan tasks, and tasks can only be assigned
    to plan members

Like database.py, every function takes an optional `db_path` and uses
parameterized SQL only.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import database as db
from database import DB_PATH

PBKDF2_ITERATIONS = 600_000
MIN_PASSWORD_LENGTH = 8
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CollabError(ValueError):
    """A rule was broken (the message is safe to show to the user)."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------
def init_collab_db(db_path: str | Path = DB_PATH) -> None:
    """Create the collaboration tables if missing. Safe to run on every start."""
    db.init_db(db_path)  # makes sure tasks exists and has the plan columns
    with closing(_connect(db_path)) as connection:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS follows (
                    follower_id INTEGER NOT NULL REFERENCES users(user_id),
                    following_id INTEGER NOT NULL REFERENCES users(user_id),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (follower_id, following_id),
                    CHECK (follower_id <> following_id)
                );

                CREATE TABLE IF NOT EXISTS plans (
                    plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                    description TEXT,
                    owner_id INTEGER NOT NULL REFERENCES users(user_id),
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS plan_members (
                    plan_id INTEGER NOT NULL REFERENCES plans(plan_id),
                    user_id INTEGER NOT NULL REFERENCES users(user_id),
                    role TEXT NOT NULL DEFAULT 'member'
                        CHECK (role IN ('owner', 'member')),
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (plan_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS plan_invitations (
                    invitation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL REFERENCES plans(plan_id),
                    inviter_id INTEGER NOT NULL REFERENCES users(user_id),
                    invitee_id INTEGER NOT NULL REFERENCES users(user_id),
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'accepted', 'rejected')),
                    created_at TEXT NOT NULL,
                    responded_at TEXT
                );

                -- at most ONE pending invitation per plan + person
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_pending_invite
                    ON plan_invitations (plan_id, invitee_id)
                    WHERE status = 'pending';

                CREATE INDEX IF NOT EXISTS idx_tasks_plan ON tasks (plan_id);

                -- sharing one personal task with a friend (request -> accept)
                CREATE TABLE IF NOT EXISTS task_shares (
                    share_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(task_id),
                    owner_id INTEGER NOT NULL REFERENCES users(user_id),
                    recipient_id INTEGER NOT NULL REFERENCES users(user_id),
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'accepted', 'rejected')),
                    created_at TEXT NOT NULL,
                    responded_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_share
                    ON task_shares (task_id, recipient_id)
                    WHERE status IN ('pending', 'accepted');
                """
            )
            # Tasks created before logins existed have no owner: give them to
            # the first registered user so nothing is lost or hidden.
            connection.execute(
                "UPDATE tasks SET created_by = (SELECT MIN(user_id) FROM users)"
                " WHERE plan_id IS NULL AND created_by IS NULL"
                " AND EXISTS (SELECT 1 FROM users)"
            )


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Return 'pbkdf2_sha256$iterations$salt$hash' with a fresh random salt."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, expected = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


# --------------------------------------------------------------------------
# Users: register / login
# --------------------------------------------------------------------------
def _public_user(row: sqlite3.Row | None) -> dict | None:
    """User dict WITHOUT the password hash."""
    if row is None:
        return None
    return {k: row[k] for k in ("user_id", "username", "email", "created_at")}


def register_user(
    username: str, email: str, password: str, db_path: str | Path = DB_PATH
) -> int:
    username, email = (username or "").strip(), (email or "").strip()
    if not USERNAME_PATTERN.match(username):
        raise CollabError(
            "Username must be 3-30 characters: letters, numbers, . _ - only."
        )
    if not EMAIL_PATTERN.match(email):
        raise CollabError("Please enter a valid email address.")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise CollabError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    password_hash = hash_password(password)
    with closing(_connect(db_path)) as connection:
        try:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO users (username, email, password_hash, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (username, email, password_hash, _now()),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError as error:
            if "email" in str(error).lower():
                raise CollabError("That email is already registered.") from error
            raise CollabError("That username is already taken.") from error


def authenticate(
    username_or_email: str, password: str, db_path: str | Path = DB_PATH
) -> dict | None:
    """Return the user (no hash) if the credentials are right, else None."""
    ident = (username_or_email or "").strip()
    with closing(_connect(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?", (ident, ident)
        ).fetchone()
    if row is None:
        # still do the hashing work so timing does not reveal valid usernames
        hash_password(password or "")
        return None
    if not verify_password(password or "", row["password_hash"]):
        return None
    return _public_user(row)


def get_user(user_id: int, db_path: str | Path = DB_PATH) -> dict | None:
    with closing(_connect(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return _public_user(row)


def search_users(
    query: str, exclude_user_id: int | None = None, db_path: str | Path = DB_PATH
) -> list[dict]:
    """Case-insensitive username search (substring). Never returns emails."""
    needle = (query or "").strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    if not needle:
        return []
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT user_id, username FROM users"
            " WHERE username LIKE ? ESCAPE '\\' AND user_id <> ?"
            " ORDER BY username LIMIT 50",
            (f"%{needle}%", exclude_user_id or -1),
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Follow system
# --------------------------------------------------------------------------
def is_following(follower_id: int, following_id: int, db_path: str | Path = DB_PATH) -> bool:
    with closing(_connect(db_path)) as connection:
        return (
            connection.execute(
                "SELECT 1 FROM follows WHERE follower_id = ? AND following_id = ?",
                (follower_id, following_id),
            ).fetchone()
            is not None
        )


def follow_user(follower_id: int, target_id: int, db_path: str | Path = DB_PATH) -> None:
    if follower_id == target_id:
        raise CollabError("You cannot follow yourself.")
    if get_user(target_id, db_path) is None:
        raise CollabError("That user does not exist.")
    with closing(_connect(db_path)) as connection:
        try:
            with connection:
                connection.execute(
                    "INSERT INTO follows (follower_id, following_id, created_at)"
                    " VALUES (?, ?, ?)",
                    (follower_id, target_id, _now()),
                )
        except sqlite3.IntegrityError as error:
            raise CollabError("You already follow this user.") from error


def unfollow_user(follower_id: int, target_id: int, db_path: str | Path = DB_PATH) -> bool:
    with closing(_connect(db_path)) as connection:
        with connection:
            cursor = connection.execute(
                "DELETE FROM follows WHERE follower_id = ? AND following_id = ?",
                (follower_id, target_id),
            )
            return cursor.rowcount > 0


def get_following(user_id: int, db_path: str | Path = DB_PATH) -> list[dict]:
    """People `user_id` follows."""
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT u.user_id, u.username FROM follows f"
            " JOIN users u ON u.user_id = f.following_id"
            " WHERE f.follower_id = ? ORDER BY u.username",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_followers(user_id: int, db_path: str | Path = DB_PATH) -> list[dict]:
    """People who follow `user_id`."""
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT u.user_id, u.username FROM follows f"
            " JOIN users u ON u.user_id = f.follower_id"
            " WHERE f.following_id = ? ORDER BY u.username",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Plans and members
# --------------------------------------------------------------------------
def create_plan(
    owner_id: int, name: str, description: str = "", db_path: str | Path = DB_PATH
) -> int:
    name = (name or "").strip()
    if not name:
        raise CollabError("Plan name cannot be empty.")
    if len(name) > 100:
        raise CollabError("Plan name must be at most 100 characters.")
    if get_user(owner_id, db_path) is None:
        raise CollabError("You must be logged in to create a plan.")
    now = _now()
    with closing(_connect(db_path)) as connection:
        with connection:
            cursor = connection.execute(
                "INSERT INTO plans (name, description, owner_id, created_at)"
                " VALUES (?, ?, ?, ?)",
                (name, description or "", owner_id, now),
            )
            plan_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO plan_members (plan_id, user_id, role, joined_at)"
                " VALUES (?, ?, 'owner', ?)",
                (plan_id, owner_id, now),
            )
            return plan_id


def is_member(plan_id: int, user_id: int, db_path: str | Path = DB_PATH) -> bool:
    with closing(_connect(db_path)) as connection:
        return (
            connection.execute(
                "SELECT 1 FROM plan_members WHERE plan_id = ? AND user_id = ?",
                (plan_id, user_id),
            ).fetchone()
            is not None
        )


def get_user_plans(user_id: int, db_path: str | Path = DB_PATH) -> list[dict]:
    """Plans the user belongs to (owner or member), newest first."""
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT p.*, m.role, o.username AS owner_name FROM plan_members m"
            " JOIN plans p ON p.plan_id = m.plan_id"
            " JOIN users o ON o.user_id = p.owner_id"
            " WHERE m.user_id = ? ORDER BY p.plan_id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_plan_members(plan_id: int, db_path: str | Path = DB_PATH) -> list[dict]:
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT u.user_id, u.username, m.role FROM plan_members m"
            " JOIN users u ON u.user_id = m.user_id"
            " WHERE m.plan_id = ? ORDER BY (m.role = 'owner') DESC, u.username",
            (plan_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Invitations (following is REQUIRED)
# --------------------------------------------------------------------------
def invite_user(
    plan_id: int, inviter_id: int, invitee_id: int, db_path: str | Path = DB_PATH
) -> int:
    if not is_member(plan_id, inviter_id, db_path):
        raise CollabError("Only members of a plan can invite people to it.")
    if inviter_id == invitee_id:
        raise CollabError("You cannot invite yourself.")
    if get_user(invitee_id, db_path) is None:
        raise CollabError("That user does not exist.")
    if not is_following(inviter_id, invitee_id, db_path):
        raise CollabError("You can only invite people you follow. Follow them first.")
    if is_member(plan_id, invitee_id, db_path):
        raise CollabError("That user is already a member of this plan.")

    with closing(_connect(db_path)) as connection:
        try:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO plan_invitations"
                    " (plan_id, inviter_id, invitee_id, status, created_at)"
                    " VALUES (?, ?, ?, 'pending', ?)",
                    (plan_id, inviter_id, invitee_id, _now()),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError as error:
            raise CollabError("An invitation to this user is already pending.") from error


def get_pending_invitations(user_id: int, db_path: str | Path = DB_PATH) -> list[dict]:
    """Invitations waiting for `user_id` to accept or reject."""
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT i.invitation_id, i.plan_id, p.name AS plan_name,"
            " u.username AS inviter_name, i.created_at"
            " FROM plan_invitations i"
            " JOIN plans p ON p.plan_id = i.plan_id"
            " JOIN users u ON u.user_id = i.inviter_id"
            " WHERE i.invitee_id = ? AND i.status = 'pending'"
            " ORDER BY i.invitation_id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_plan_pending_invitations(plan_id: int, db_path: str | Path = DB_PATH) -> list[dict]:
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT i.invitation_id, u.username AS invitee_name, i.invitee_id"
            " FROM plan_invitations i JOIN users u ON u.user_id = i.invitee_id"
            " WHERE i.plan_id = ? AND i.status = 'pending' ORDER BY i.invitation_id",
            (plan_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def respond_to_invitation(
    invitation_id: int, user_id: int, accept: bool, db_path: str | Path = DB_PATH
) -> None:
    """Accept or reject. Only the invited user can respond, and only once."""
    with closing(_connect(db_path)) as connection:
        with connection:
            row = connection.execute(
                "SELECT * FROM plan_invitations WHERE invitation_id = ?",
                (invitation_id,),
            ).fetchone()
            if row is None or row["invitee_id"] != user_id:
                raise CollabError("Invitation not found.")
            if row["status"] != "pending":
                raise CollabError("This invitation was already answered.")
            now = _now()
            connection.execute(
                "UPDATE plan_invitations SET status = ?, responded_at = ?"
                " WHERE invitation_id = ?",
                ("accepted" if accept else "rejected", now, invitation_id),
            )
            if accept:
                connection.execute(
                    "INSERT OR IGNORE INTO plan_members (plan_id, user_id, role, joined_at)"
                    " VALUES (?, ?, 'member', ?)",
                    (row["plan_id"], user_id, now),
                )


# --------------------------------------------------------------------------
# Collaborative tasks (stored in the existing tasks table, plan_id set)
# --------------------------------------------------------------------------
def add_plan_task(
    plan_id: int,
    creator_id: int,
    title: str,
    description: str = "",
    category: str = "",
    priority: str = "Medium",
    due_date: str | None = None,
    assigned_to: int | None = None,
    db_path: str | Path = DB_PATH,
) -> int:
    if not is_member(plan_id, creator_id, db_path):
        raise CollabError("Only members of a plan can add tasks to it.")
    if assigned_to is not None and not is_member(plan_id, assigned_to, db_path):
        raise CollabError("Tasks can only be assigned to members of the plan.")
    try:
        db._check_fields(title, priority, "Pending", due_date)  # same rules as personal tasks
    except ValueError as error:
        raise CollabError(str(error)) from error

    with closing(_connect(db_path)) as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO tasks (title, description, category, priority, status,
                                   due_date, created_at, plan_id, assigned_to, created_by)
                VALUES (?, ?, ?, ?, 'Pending', ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(), description, category, priority, due_date,
                    _now(), plan_id, assigned_to, creator_id,
                ),
            )
            return cursor.lastrowid


def get_plan_tasks(plan_id: int, db_path: str | Path = DB_PATH) -> list[dict]:
    """Tasks of a plan, with creator and assignee names. Oldest first."""
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT t.*, c.username AS creator_name, a.username AS assignee_name"
            " FROM tasks t"
            " LEFT JOIN users c ON c.user_id = t.created_by"
            " LEFT JOIN users a ON a.user_id = t.assigned_to"
            " WHERE t.plan_id = ? ORDER BY t.task_id",
            (plan_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _plan_task_for_member(task_id: int, user_id: int, db_path) -> dict:
    task = db.get_task(task_id, db_path)
    if task is None or task.get("plan_id") is None or not is_member(
        task["plan_id"], user_id, db_path
    ):
        raise CollabError("Task not found.")
    return task


def set_plan_task_status(
    task_id: int, user_id: int, status: str, db_path: str | Path = DB_PATH
) -> None:
    """Any plan member can change a shared task's status."""
    _plan_task_for_member(task_id, user_id, db_path)
    try:
        db.update_status(task_id, status, db_path)
    except ValueError as error:
        raise CollabError(str(error)) from error


def delete_plan_task(task_id: int, user_id: int, db_path: str | Path = DB_PATH) -> None:
    """Only the task's creator or the plan owner can delete it."""
    task = _plan_task_for_member(task_id, user_id, db_path)
    plan_owner = [m for m in get_plan_members(task["plan_id"], db_path) if m["role"] == "owner"]
    if user_id != task.get("created_by") and not any(m["user_id"] == user_id for m in plan_owner):
        raise CollabError("Only the task creator or the plan owner can delete this task.")
    db.delete_task(task_id, db_path)


# --------------------------------------------------------------------------
# Shared progress
# --------------------------------------------------------------------------
def plan_progress(plan_id: int, db_path: str | Path = DB_PATH, today=None) -> dict:
    """Dashboard numbers for one plan.

    Reuses task_logic.calculate_stats so the counts follow the SAME rules as the
    existing dashboard (completed + pending + overdue == total).
    Adds `per_member`: tasks assigned to each member (every member is listed,
    even with 0), plus an 'Unassigned' row when such tasks exist.
    """
    import task_logic as logic

    tasks = get_plan_tasks(plan_id, db_path)
    stats = logic.calculate_stats(tasks, today)

    per_member = []
    for member in get_plan_members(plan_id, db_path):
        mine = [t for t in tasks if t["assigned_to"] == member["user_id"]]
        s = logic.calculate_stats(mine, today)
        per_member.append(
            {"username": member["username"], "assigned": s["total"],
             "completed": s["completed"], "pending": s["pending"],
             "overdue": s["overdue"]}
        )
    loose = [t for t in tasks if t["assigned_to"] is None]
    if loose:
        s = logic.calculate_stats(loose, today)
        per_member.append(
            {"username": "Unassigned", "assigned": s["total"],
             "completed": s["completed"], "pending": s["pending"],
             "overdue": s["overdue"]}
        )
    stats["per_member"] = per_member
    return stats


# --------------------------------------------------------------------------
# Personal tasks per user + sharing a task with a friend
# --------------------------------------------------------------------------
def get_user_tasks(user_id: int, db_path: str | Path = DB_PATH) -> list[dict]:
    """Personal tasks this user can see: their own + tasks shared with them
    (accepted). Plan tasks are not included. Each dict also has:
      shared_by   - owner's username when someone shared it with you, else None
      shared_with - usernames you shared your own task with (accepted/pending)
    """
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT t.*, u.username AS owner_name FROM tasks t"
            " LEFT JOIN users u ON u.user_id = t.created_by"
            " WHERE t.plan_id IS NULL AND (t.created_by = ? OR t.task_id IN ("
            "   SELECT task_id FROM task_shares"
            "   WHERE recipient_id = ? AND status = 'accepted'))"
            " ORDER BY t.task_id",
            (user_id, user_id),
        ).fetchall()
        shares = connection.execute(
            "SELECT s.task_id, u.username, s.status FROM task_shares s"
            " JOIN users u ON u.user_id = s.recipient_id"
            " WHERE s.owner_id = ? AND s.status IN ('pending', 'accepted')"
            " ORDER BY u.username",
            (user_id,),
        ).fetchall()
    shared_with: dict[int, list[str]] = {}
    for share in shares:
        label = share["username"] + (" (pending)" if share["status"] == "pending" else "")
        shared_with.setdefault(share["task_id"], []).append(label)
    tasks = []
    for row in rows:
        task = dict(row)
        task["shared_by"] = task["owner_name"] if task["created_by"] != user_id else None
        task["shared_with"] = shared_with.get(task["task_id"], [])
        tasks.append(task)
    return tasks


def share_task(
    task_id: int, owner_id: int, recipient_id: int, db_path: str | Path = DB_PATH
) -> int:
    """Send a share request. Only the task's owner can share it."""
    task = db.get_task(task_id, db_path)
    if task is None or task.get("plan_id") is not None or task.get("created_by") != owner_id:
        raise CollabError("You can only share your own tasks.")
    if owner_id == recipient_id:
        raise CollabError("You cannot share a task with yourself.")
    if get_user(recipient_id, db_path) is None:
        raise CollabError("That user does not exist.")
    with closing(_connect(db_path)) as connection:
        try:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO task_shares (task_id, owner_id, recipient_id, status, created_at)"
                    " VALUES (?, ?, ?, 'pending', ?)",
                    (task_id, owner_id, recipient_id, _now()),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError as error:
            raise CollabError("This task is already shared with (or requested from) that user.") from error


def get_task_shares(task_id: int, db_path: str | Path = DB_PATH) -> list[dict]:
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT s.share_id, s.recipient_id, u.username, s.status FROM task_shares s"
            " JOIN users u ON u.user_id = s.recipient_id"
            " WHERE s.task_id = ? AND s.status IN ('pending', 'accepted')"
            " ORDER BY u.username",
            (task_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def revoke_task_share(share_id: int, owner_id: int, db_path: str | Path = DB_PATH) -> bool:
    """Owner cancels a pending request or stops sharing with someone."""
    with closing(_connect(db_path)) as connection:
        with connection:
            cursor = connection.execute(
                "DELETE FROM task_shares WHERE share_id = ? AND owner_id = ?"
                " AND status IN ('pending', 'accepted')",
                (share_id, owner_id),
            )
            return cursor.rowcount > 0


def get_pending_task_shares(user_id: int, db_path: str | Path = DB_PATH) -> list[dict]:
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT s.share_id, s.task_id, t.title AS task_title, o.username AS owner_name"
            " FROM task_shares s"
            " JOIN tasks t ON t.task_id = s.task_id"
            " JOIN users o ON o.user_id = s.owner_id"
            " WHERE s.recipient_id = ? AND s.status = 'pending'"
            " ORDER BY s.share_id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def respond_to_task_share(
    share_id: int, user_id: int, accept: bool, db_path: str | Path = DB_PATH
) -> None:
    """Only the person the task was shared with can accept or reject."""
    with closing(_connect(db_path)) as connection:
        with connection:
            row = connection.execute(
                "SELECT * FROM task_shares WHERE share_id = ?", (share_id,)
            ).fetchone()
            if row is None or row["recipient_id"] != user_id:
                raise CollabError("Request not found.")
            if row["status"] != "pending":
                raise CollabError("This request was already answered.")
            if connection.execute(
                "SELECT 1 FROM tasks WHERE task_id = ?", (row["task_id"],)
            ).fetchone() is None:
                raise CollabError("That task no longer exists.")
            connection.execute(
                "UPDATE task_shares SET status = ?, responded_at = ? WHERE share_id = ?",
                ("accepted" if accept else "rejected", _now(), share_id),
            )


def count_pending_requests(user_id: int, db_path: str | Path = DB_PATH) -> int:
    """Plan invitations + task share requests waiting for this user."""
    return len(get_pending_invitations(user_id, db_path)) + len(
        get_pending_task_shares(user_id, db_path)
    )
