"""Tests for the Collaborative Planning feature (data layer)."""

import sqlite3
from datetime import date, timedelta

import pytest

import collab_db as c
import database as db
from collab_db import CollabError


@pytest.fixture
def path(tmp_path):
    p = tmp_path / "tasks.db"
    c.init_collab_db(p)
    return p


@pytest.fixture
def users(path):
    ids = {n: c.register_user(n, f"{n}@x.com", "password123", path) for n in ("alice", "bob", "carol")}
    return ids


# ---- migration: existing data is untouched ---------------------------------
def test_existing_database_is_migrated_not_recreated(tmp_path):
    p = tmp_path / "old.db"
    with sqlite3.connect(p) as con:  # an OLD database, created before this feature
        con.execute("""CREATE TABLE tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, description TEXT, category TEXT,
            priority TEXT NOT NULL, status TEXT NOT NULL, due_date TEXT,
            created_at TEXT NOT NULL)""")
        con.execute("INSERT INTO tasks (title,priority,status,created_at) VALUES ('Old','High','Pending','2026-01-01')")
    c.init_collab_db(p)
    c.init_collab_db(p)  # idempotent
    tasks = db.get_all_tasks(p)
    assert [t["title"] for t in tasks] == ["Old"]
    assert tasks[0]["plan_id"] is None


def test_plan_tasks_do_not_leak_into_personal_tasks(path, users):
    db.add_task("Personal", db_path=path)
    plan = c.create_plan(users["alice"], "P", db_path=path)
    c.add_plan_task(plan, users["alice"], "Shared", db_path=path)
    assert [t["title"] for t in db.get_all_tasks(path)] == ["Personal"]


# ---- registration / login --------------------------------------------------
def test_password_is_hashed(path, users):
    with sqlite3.connect(path) as con:
        stored = con.execute("SELECT password_hash FROM users WHERE username='alice'").fetchone()[0]
    assert "password123" not in stored and stored.startswith("pbkdf2_sha256$")


def test_login_success_and_failure(path, users):
    assert c.authenticate("alice", "password123", path)["user_id"] == users["alice"]
    assert c.authenticate("ALICE@x.com", "password123", path)["username"] == "alice"
    assert c.authenticate("alice", "wrong", path) is None
    assert c.authenticate("nobody", "password123", path) is None
    assert "password_hash" not in c.authenticate("alice", "password123", path)


@pytest.mark.parametrize("u,e,p", [("ab", "a@b.co", "password1"), ("good", "bad", "password1"),
                                   ("good", "a@b.co", "short")])
def test_registration_validation(path, u, e, p):
    with pytest.raises(CollabError):
        c.register_user(u, e, p, path)


def test_duplicate_username_and_email(path, users):
    with pytest.raises(CollabError, match="username"):
        c.register_user("ALICE", "new@x.com", "password123", path)
    with pytest.raises(CollabError, match="email"):
        c.register_user("new", "Alice@X.com", "password123", path)


# ---- follow ----------------------------------------------------------------
def test_follow_rules(path, users):
    a, b = users["alice"], users["bob"]
    with pytest.raises(CollabError, match="yourself"):
        c.follow_user(a, a, path)
    c.follow_user(a, b, path)
    with pytest.raises(CollabError, match="already"):
        c.follow_user(a, b, path)
    assert [u["username"] for u in c.get_following(a, path)] == ["bob"]
    assert [u["username"] for u in c.get_followers(b, path)] == ["alice"]
    assert c.get_followers(a, path) == []
    assert c.unfollow_user(a, b, path) is True
    assert c.unfollow_user(a, b, path) is False
    assert c.get_following(a, path) == []


def test_search_users(path, users):
    assert [u["username"] for u in c.search_users("AL", users["bob"], path)] == ["alice"]
    assert c.search_users("bob", users["bob"], path) == []  # excludes self
    assert c.search_users("%", None, path) == []             # wildcard is escaped
    assert "email" not in c.search_users("a", None, path)[0]


# ---- plans + invitations ---------------------------------------------------
def test_creator_is_owner(path, users):
    plan = c.create_plan(users["alice"], "AIML Exam Preparation", db_path=path)
    assert c.get_plan_members(plan, path) == [{"user_id": users["alice"], "username": "alice", "role": "owner"}]
    assert c.get_user_plans(users["alice"], path)[0]["role"] == "owner"
    with pytest.raises(CollabError):
        c.create_plan(users["alice"], "   ", db_path=path)


def test_cannot_invite_without_following(path, users):
    plan = c.create_plan(users["alice"], "P", db_path=path)
    with pytest.raises(CollabError, match="follow"):
        c.invite_user(plan, users["alice"], users["bob"], path)
    # following in the OTHER direction does not count
    c.follow_user(users["bob"], users["alice"], path)
    with pytest.raises(CollabError, match="follow"):
        c.invite_user(plan, users["alice"], users["bob"], path)


def test_invite_accept_flow(path, users):
    a, b = users["alice"], users["bob"]
    plan = c.create_plan(a, "P", db_path=path)
    c.follow_user(a, b, path)
    c.invite_user(plan, a, b, path)
    with pytest.raises(CollabError, match="pending"):
        c.invite_user(plan, a, b, path)  # duplicate pending
    inv = c.get_pending_invitations(b, path)
    assert len(inv) == 1 and inv[0]["plan_name"] == "P" and inv[0]["inviter_name"] == "alice"
    with pytest.raises(CollabError):  # someone else cannot answer it
        c.respond_to_invitation(inv[0]["invitation_id"], users["carol"], True, path)
    c.respond_to_invitation(inv[0]["invitation_id"], b, True, path)
    assert c.is_member(plan, b, path)
    assert c.get_pending_invitations(b, path) == []
    with pytest.raises(CollabError, match="answered"):
        c.respond_to_invitation(inv[0]["invitation_id"], b, True, path)
    with pytest.raises(CollabError, match="already a member"):
        c.invite_user(plan, a, b, path)


def test_reject_then_reinvite(path, users):
    a, b = users["alice"], users["bob"]
    plan = c.create_plan(a, "P", db_path=path)
    c.follow_user(a, b, path)
    inv = c.invite_user(plan, a, b, path)
    c.respond_to_invitation(inv, b, False, path)
    assert not c.is_member(plan, b, path)
    c.invite_user(plan, a, b, path)  # allowed again after a rejection


def test_non_member_cannot_invite(path, users):
    plan = c.create_plan(users["alice"], "P", db_path=path)
    c.follow_user(users["bob"], users["carol"], path)
    with pytest.raises(CollabError, match="members"):
        c.invite_user(plan, users["bob"], users["carol"], path)


# ---- shared tasks ----------------------------------------------------------
def _team(path, users):
    a, b = users["alice"], users["bob"]
    plan = c.create_plan(a, "P", db_path=path)
    c.follow_user(a, b, path)
    c.respond_to_invitation(c.invite_user(plan, a, b, path), b, True, path)
    return plan


def test_shared_tasks_visibility_and_assignment(path, users):
    plan = _team(path, users)
    a, b, carol = users["alice"], users["bob"], users["carol"]
    t = c.add_plan_task(plan, b, "Read ch.1", priority="High", due_date="2026-12-01", assigned_to=a, db_path=path)
    task = c.get_plan_tasks(plan, path)[0]
    assert (task["creator_name"], task["assignee_name"], task["task_id"]) == ("bob", "alice", t)
    with pytest.raises(CollabError, match="members"):
        c.add_plan_task(plan, carol, "x", db_path=path)         # outsider cannot add
    with pytest.raises(CollabError, match="assigned"):
        c.add_plan_task(plan, a, "x", assigned_to=carol, db_path=path)  # outsider cannot be assignee
    with pytest.raises(CollabError):
        c.add_plan_task(plan, a, "  ", db_path=path)
    c.set_plan_task_status(t, a, "Completed", path)
    assert c.get_plan_tasks(plan, path)[0]["status"] == "Completed"
    with pytest.raises(CollabError):
        c.set_plan_task_status(t, carol, "Pending", path)       # outsider cannot edit
    with pytest.raises(CollabError, match="creator or the plan owner"):
        c.add_plan_task(plan, a, "Alice's", db_path=path)
        other = c.get_plan_tasks(plan, path)[-1]["task_id"]
        c.delete_plan_task(other, b, path)                      # bob is neither creator nor owner
    c.delete_plan_task(t, a, path)                              # owner may delete bob's task
    assert all(x["task_id"] != t for x in c.get_plan_tasks(plan, path))


def test_personal_task_cannot_be_changed_via_collab_api(path, users):
    tid = db.add_task("mine", db_path=path)
    with pytest.raises(CollabError):
        c.set_plan_task_status(tid, users["alice"], "Completed", path)
    with pytest.raises(CollabError):
        c.delete_plan_task(tid, users["alice"], path)


def test_progress_dashboard(path, users):
    plan = _team(path, users)
    a, b = users["alice"], users["bob"]
    past = (date.today() - timedelta(days=3)).isoformat()
    future = (date.today() + timedelta(days=3)).isoformat()
    t1 = c.add_plan_task(plan, a, "done", due_date=future, assigned_to=a, db_path=path)
    c.add_plan_task(plan, a, "late", due_date=past, assigned_to=b, db_path=path)
    c.add_plan_task(plan, a, "todo", due_date=future, assigned_to=b, db_path=path)
    c.add_plan_task(plan, b, "nobody", due_date=future, db_path=path)
    c.set_plan_task_status(t1, a, "Completed", path)
    s = c.plan_progress(plan, path)
    assert (s["total"], s["completed"], s["pending"], s["overdue"], s["completion_percentage"]) == (4, 1, 2, 1, 25.0)
    rows = {r["username"]: r for r in s["per_member"]}
    assert rows["alice"]["assigned"] == 1 and rows["alice"]["completed"] == 1
    assert rows["bob"]["assigned"] == 2 and rows["bob"]["overdue"] == 1
    assert rows["Unassigned"]["assigned"] == 1


def test_empty_plan_progress(path, users):
    plan = c.create_plan(users["alice"], "P", db_path=path)
    s = c.plan_progress(plan, path)
    assert s["total"] == 0 and s["completion_percentage"] == 0.0
    assert s["per_member"][0]["assigned"] == 0


# ---- personal tasks per user + sharing a task -----------------------------
def test_each_user_sees_only_their_own_tasks(path, users):
    a, b = users["alice"], users["bob"]
    db.add_task("A's", db_path=path, owner_id=a)
    db.add_task("B's", db_path=path, owner_id=b)
    assert [t["title"] for t in c.get_user_tasks(a, path)] == ["A's"]
    assert [t["title"] for t in c.get_user_tasks(b, path)] == ["B's"]


def test_legacy_tasks_go_to_first_user(tmp_path):
    p = tmp_path / "t.db"
    c.init_collab_db(p)
    db.add_task("old task", db_path=p)            # created before any login existed
    first = c.register_user("first", "f@x.com", "password123", p)
    second = c.register_user("second", "s@x.com", "password123", p)
    c.init_collab_db(p)                            # app start / rerun
    assert [t["title"] for t in c.get_user_tasks(first, p)] == ["old task"]
    assert c.get_user_tasks(second, p) == []


def test_share_task_request_accept_flow(path, users):
    a, b, carol = users["alice"], users["bob"], users["carol"]
    tid = db.add_task("Study", db_path=path, owner_id=a)
    c.share_task(tid, a, b, path)
    assert c.get_user_tasks(b, path) == []                       # not yet accepted
    req = c.get_pending_task_shares(b, path)
    assert req[0]["task_title"] == "Study" and req[0]["owner_name"] == "alice"
    assert c.count_pending_requests(b, path) == 1
    with pytest.raises(CollabError):
        c.respond_to_task_share(req[0]["share_id"], carol, True, path)   # not for carol
    c.respond_to_task_share(req[0]["share_id"], b, True, path)
    seen = c.get_user_tasks(b, path)
    assert [t["title"] for t in seen] == ["Study"] and seen[0]["shared_by"] == "alice"
    assert c.get_user_tasks(a, path)[0]["shared_with"] == ["bob"]
    # status changes made by bob are the same task alice sees
    db.update_status(tid, "Completed", path)
    assert c.get_user_tasks(a, path)[0]["status"] == "Completed"
    with pytest.raises(CollabError):
        c.share_task(tid, a, b, path)                            # already shared


def test_share_rules(path, users):
    a, b = users["alice"], users["bob"]
    tid = db.add_task("Study", db_path=path, owner_id=a)
    with pytest.raises(CollabError, match="yourself"):
        c.share_task(tid, a, a, path)
    with pytest.raises(CollabError, match="your own"):
        c.share_task(tid, b, a, path)                            # bob does not own it
    c.share_task(tid, a, b, path)
    with pytest.raises(CollabError, match="already"):
        c.share_task(tid, a, b, path)                            # duplicate pending


def test_reject_and_revoke_share(path, users):
    a, b = users["alice"], users["bob"]
    tid = db.add_task("Study", db_path=path, owner_id=a)
    sid = c.share_task(tid, a, b, path)
    c.respond_to_task_share(sid, b, False, path)
    assert c.get_user_tasks(b, path) == []
    sid2 = c.share_task(tid, a, b, path)                         # can ask again after reject
    c.respond_to_task_share(sid2, b, True, path)
    assert len(c.get_user_tasks(b, path)) == 1
    assert c.revoke_task_share(sid2, a, path) is True
    assert c.get_user_tasks(b, path) == []
