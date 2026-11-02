"""Collaborative Planning - Streamlit pages.

UI only; all rules live in collab_db.py. app.py calls these page functions.
The logged-in user is kept in st.session_state["user"] (a dict without the
password hash). Existing task pages never need a login.
"""

import re
import sqlite3
from datetime import date

import streamlit as st

import collab_db as cdb
import task_logic as logic

COLLAB_PAGES = ["People", "Collaborative Plans", "Invitations"]
COLLAB_ICONS = {
    "People": "🤝",
    "Collaborative Plans": "👥",
    "Invitations": "📨",
}

PRIORITY_BADGE = {
    "High": ":red-badge[🔴 High]",
    "Medium": ":orange-badge[🟠 Medium]",
    "Low": ":green-badge[🟢 Low]",
}
STATUS_BADGE = {
    "Pending": ":gray-badge[Pending]",
    "In Progress": ":blue-badge[In Progress]",
    "Completed": ":green-badge[✅ Completed]",
}
DEADLINE_COLOR = {
    "overdue": "red", "today": "orange", "soon": "orange",
    "later": "gray", "none": "gray", "completed": "green",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def md_safe(text: object) -> str:
    return re.sub(r"([!-/:-@\[-`{-~])", r"\\\1", str(text or ""))


def flash(message: str, kind: str = "success") -> None:
    """Same mechanism as app.py: shown at the top of the next run."""
    st.session_state["flash"] = (kind, message)


def current_user() -> dict | None:
    return st.session_state.get("user")


def require_login() -> dict | None:
    """Return the logged-in user, or show a hint and return None."""
    user = current_user()
    if user is None:  # app.py shows the login screen first, so this is only a safety net
        st.info("Please log in first.")
    return user


def _run(action, success: str | None = None) -> bool:
    """Run a data-layer call, turning rule violations into a visible error."""
    try:
        action()
    except (cdb.CollabError, sqlite3.Error) as error:
        flash(str(error), "error")
        return False
    if success:
        flash(success)
    return True


def logout() -> None:
    for key in ("user", "collab_plan_id", "collab_confirm_delete", "sharing_id",
                "last_added_id", "page"):
        st.session_state.pop(key, None)
    flash("You have been logged out.", "info")


def render_sidebar_account() -> None:
    """Small block under the navigation: who is logged in + pending invites."""
    user = current_user()
    st.divider()
    if user is None:
        st.caption("👤 Not logged in")
        return
    st.caption(f"👤 Logged in as **{md_safe(user['username'])}**")
    pending = cdb.count_pending_requests(user["user_id"])
    if pending:
        st.caption(f"📨 {pending} pending request{'s' if pending != 1 else ''}")
    st.button("Log out", key="sidebar_logout", on_click=logout)


# --------------------------------------------------------------------------
# Account: register / login / logout
# --------------------------------------------------------------------------
def page_auth() -> None:
    """Login / register screen. app.py shows it first, before anything else."""
    st.title("✅ Smart Task Manager")
    st.caption("Log in or create an account to manage and share your tasks.")
    login_tab, register_tab = st.tabs(["Log in", "Create account"])
    with login_tab:
        with st.form("login_form"):
            ident = st.text_input("Username or email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            found = cdb.authenticate(ident, password)
            if found is None:
                st.error("Wrong username/email or password.")
            else:
                st.session_state["user"] = found
                st.session_state.pop("collab_plan_id", None)
                flash(f"Welcome back, {found['username']}!")
                st.rerun()

    with register_tab:
        with st.form("register_form"):
            username = st.text_input("Username", help="3-30 letters, numbers, . _ -")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password", help="At least 8 characters")
            confirm = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account", type="primary")
        if submitted:
            if password != confirm:
                st.error("The two passwords do not match.")
            else:
                try:
                    cdb.register_user(username, email, password)
                except (cdb.CollabError, sqlite3.Error) as error:
                    st.error(str(error))
                else:
                    st.session_state["user"] = cdb.authenticate(username, password)
                    st.session_state.pop("collab_plan_id", None)
                    flash("Account created. You are now logged in.")
                    st.rerun()


# --------------------------------------------------------------------------
# People: search, follow, followers / following
# --------------------------------------------------------------------------
def _follow(me: int, other: int) -> None:
    _run(lambda: cdb.follow_user(me, other), "Now following.")


def _unfollow(me: int, other: int) -> None:
    _run(lambda: cdb.unfollow_user(me, other), "Unfollowed.")


def page_people() -> None:
    st.header("🤝 People")
    user = require_login()
    if user is None:
        return
    me = user["user_id"]

    query = st.text_input("🔍 Search users by username", key="people_search")
    if query.strip():
        results = cdb.search_users(query, exclude_user_id=me)
        if not results:
            st.warning("No users found.")
        for person in results:
            with st.container(border=True):
                name_col, btn_col = st.columns([4, 1])
                name_col.markdown(f"**{md_safe(person['username'])}**")
                if cdb.is_following(me, person["user_id"]):
                    btn_col.button("Unfollow", key=f"search_unf_{person['user_id']}",
                                   on_click=_unfollow, args=(me, person["user_id"]),
                                   use_container_width=True)
                else:
                    btn_col.button("Follow", key=f"search_fol_{person['user_id']}",
                                   type="primary", on_click=_follow,
                                   args=(me, person["user_id"]), use_container_width=True)

    following = cdb.get_following(me)
    followers = cdb.get_followers(me)
    following_ids = {p["user_id"] for p in following}
    following_tab, followers_tab = st.tabs(
        [f"Following ({len(following)})", f"Followers ({len(followers)})"]
    )
    with following_tab:
        if not following:
            st.caption("You are not following anyone yet. Search for a username above.")
        for person in following:
            name_col, btn_col = st.columns([4, 1])
            name_col.markdown(f"**{md_safe(person['username'])}**")
            btn_col.button("Unfollow", key=f"fing_unf_{person['user_id']}",
                           on_click=_unfollow, args=(me, person["user_id"]),
                           use_container_width=True)
    with followers_tab:
        if not followers:
            st.caption("Nobody follows you yet.")
        for person in followers:
            name_col, btn_col = st.columns([4, 1])
            name_col.markdown(f"**{md_safe(person['username'])}**")
            if person["user_id"] not in following_ids:
                btn_col.button("Follow back", key=f"fers_fol_{person['user_id']}",
                               on_click=_follow, args=(me, person["user_id"]),
                               use_container_width=True)
            else:
                btn_col.caption("Following")


# --------------------------------------------------------------------------
# Invitations inbox
# --------------------------------------------------------------------------
def _answer(invitation_id: int, me: int, accept: bool) -> None:
    _run(
        lambda: cdb.respond_to_invitation(invitation_id, me, accept),
        "Invitation accepted. You are now a member of the plan." if accept
        else "Invitation rejected.",
    )


def _answer_share(share_id: int, me: int, accept: bool) -> None:
    _run(
        lambda: cdb.respond_to_task_share(share_id, me, accept),
        "Task accepted. It now appears in your dashboard and task lists." if accept
        else "Request rejected.",
    )


def page_invitations() -> None:
    st.header("📨 Invitations")
    user = require_login()
    if user is None:
        return
    me = user["user_id"]
    shares = cdb.get_pending_task_shares(me)
    invites = cdb.get_pending_invitations(me)
    if not invites and not shares:
        st.info("You have no pending requests.")
        return
    if shares:
        st.subheader("📋 Task share requests")
    for sh in shares:
        with st.container(border=True):
            st.markdown(
                f"**{md_safe(sh['owner_name'])}** wants to share the task "
                f"**{md_safe(sh['task_title'])}** with you"
            )
            accept_col, reject_col, _ = st.columns([1, 1, 3])
            accept_col.button("✅ Accept", key=f"sh_acc_{sh['share_id']}", type="primary",
                              on_click=_answer_share, args=(sh["share_id"], me, True),
                              use_container_width=True)
            reject_col.button("Reject", key=f"sh_rej_{sh['share_id']}",
                              on_click=_answer_share, args=(sh["share_id"], me, False),
                              use_container_width=True)
    if invites:
        st.subheader("👥 Plan invitations")
    for inv in invites:
        with st.container(border=True):
            st.markdown(
                f"**{md_safe(inv['inviter_name'])}** invited you to join "
                f"**{md_safe(inv['plan_name'])}**"
            )
            accept_col, reject_col, _ = st.columns([1, 1, 3])
            accept_col.button("✅ Accept", key=f"inv_acc_{inv['invitation_id']}",
                              type="primary", on_click=_answer,
                              args=(inv["invitation_id"], me, True),
                              use_container_width=True)
            reject_col.button("Reject", key=f"inv_rej_{inv['invitation_id']}",
                              on_click=_answer,
                              args=(inv["invitation_id"], me, False),
                              use_container_width=True)


# --------------------------------------------------------------------------
# Collaborative plans
# --------------------------------------------------------------------------
def _set_status(task_id: int, me: int, status: str) -> None:
    _run(lambda: cdb.set_plan_task_status(task_id, me, status), f"Task marked as {status}.")


def _ask_delete(task_id: int) -> None:
    st.session_state["collab_confirm_delete"] = task_id


def _cancel_delete() -> None:
    st.session_state.pop("collab_confirm_delete", None)


def _confirm_delete(task_id: int, me: int) -> None:
    _run(lambda: cdb.delete_plan_task(task_id, me), "Task deleted.")
    st.session_state.pop("collab_confirm_delete", None)


def _render_plan_task(task: dict, me: int, plan_owner_id: int) -> None:
    task_id = task["task_id"]
    with st.container(border=True):
        st.markdown(f"**{md_safe(task['title'])}**")
        parts = [
            PRIORITY_BADGE.get(task["priority"], md_safe(task["priority"])),
            STATUS_BADGE.get(task["status"], md_safe(task["status"])),
        ]
        if task.get("category"):
            parts.append(f":violet-badge[{md_safe(task['category'])}]")
        due = logic.parse_due_date(task["due_date"])
        if due:
            state = logic.deadline_status(task)
            label = f"📅 {due:%d %b %Y}"
            if state != "completed":
                label += f" · {logic.deadline_label(task)}"
            parts.append(f":{DEADLINE_COLOR[state]}-badge[{label}]")
        st.markdown(" ".join(parts))
        if task.get("description"):
            st.caption(md_safe(task["description"]))
        st.caption(
            f"🧑 Created by **{md_safe(task.get('creator_name') or 'unknown')}** · "
            f"🎯 Assigned to **{md_safe(task.get('assignee_name') or 'nobody')}**"
        )

        can_delete = me in (task.get("created_by"), plan_owner_id)
        if st.session_state.get("collab_confirm_delete") == task_id:
            st.warning("Delete this shared task permanently?")
            yes_col, no_col, _ = st.columns([1, 1, 3])
            yes_col.button("Yes, delete", key=f"cp_yes_{task_id}", type="primary",
                           on_click=_confirm_delete, args=(task_id, me),
                           use_container_width=True)
            no_col.button("Cancel", key=f"cp_no_{task_id}", on_click=_cancel_delete,
                          use_container_width=True)
            return

        cols = st.columns([1, 1, 1, 3])
        slot = 0
        if task["status"] == "Pending":
            cols[slot].button("▶ Start", key=f"cp_start_{task_id}", on_click=_set_status,
                              args=(task_id, me, "In Progress"), use_container_width=True)
            slot += 1
        if task["status"] != "Completed":
            cols[slot].button("✅ Done", key=f"cp_done_{task_id}", on_click=_set_status,
                              args=(task_id, me, "Completed"), use_container_width=True)
        else:
            cols[slot].button("↩ Reopen", key=f"cp_reopen_{task_id}", on_click=_set_status,
                              args=(task_id, me, "Pending"), use_container_width=True)
        if can_delete:
            cols[2].button("🗑 Delete", key=f"cp_del_{task_id}", on_click=_ask_delete,
                           args=(task_id,), use_container_width=True)


def _render_progress(plan_id: int) -> None:
    stats = cdb.plan_progress(plan_id)
    cols = st.columns(5)
    cols[0].metric("Total tasks", stats["total"])
    cols[1].metric("Completed", stats["completed"])
    cols[2].metric("Pending", stats["pending"])
    cols[3].metric("Overdue", stats["overdue"])
    cols[4].metric("Completion", f"{stats['completion_percentage']}%")
    st.progress(
        stats["completion_percentage"] / 100,
        text=f"Plan completion: {stats['completed']} of {stats['total']} tasks "
             f"({stats['completion_percentage']}%)",
    )
    st.markdown("**Tasks assigned to each member**")
    st.dataframe(
        [
            {"Member": r["username"], "Assigned": r["assigned"], "Completed": r["completed"],
             "Pending": r["pending"], "Overdue": r["overdue"]}
            for r in stats["per_member"]
        ],
        hide_index=True,
    )


def _render_invite(plan_id: int, me: int, members: list[dict]) -> None:
    member_ids = {m["user_id"] for m in members}
    pending_ids = {i["invitee_id"] for i in cdb.get_plan_pending_invitations(plan_id)}
    candidates = [
        p for p in cdb.get_following(me)
        if p["user_id"] not in member_ids and p["user_id"] not in pending_ids
    ]
    st.caption("You can only invite people you follow. Find people on the **People** page.")
    pending = cdb.get_plan_pending_invitations(plan_id)
    if pending:
        st.caption("⏳ Pending: " + ", ".join(md_safe(i["invitee_name"]) for i in pending))
    if not candidates:
        st.info("No one to invite right now. Follow more people first.")
        return
    with st.form(f"invite_form_{plan_id}", clear_on_submit=True):
        chosen = st.selectbox("Invite", candidates, format_func=lambda p: p["username"])
        sent = st.form_submit_button("Send invitation", type="primary")
    if sent:
        try:
            cdb.invite_user(plan_id, me, chosen["user_id"])
        except (cdb.CollabError, sqlite3.Error) as error:
            st.error(str(error))
        else:
            flash(f"Invitation sent to {chosen['username']}.")
            st.rerun()


def _render_add_task(plan_id: int, me: int, members: list[dict]) -> None:
    with st.form(f"plan_task_form_{plan_id}", clear_on_submit=True):
        title = st.text_input("Title *", max_chars=100)
        description = st.text_area("Description")
        c1, c2, c3, c4 = st.columns(4)
        category = c1.selectbox("Category", logic.CATEGORIES)
        priority = c2.selectbox("Priority", logic.PRIORITIES, index=1)
        due = c3.date_input("Due date", value=date.today(), format="DD/MM/YYYY")
        assignee = c4.selectbox(
            "Assign to", [None, *members],
            format_func=lambda m: "Unassigned" if m is None else m["username"],
        )
        submitted = st.form_submit_button("Add shared task", type="primary")
    if not submitted:
        return
    errors = logic.validate_task(title, priority, due)
    if errors:
        for message in errors:
            st.error(message)
        return
    try:
        cdb.add_plan_task(
            plan_id, me, title, description, category, priority, due.isoformat(),
            assignee["user_id"] if assignee else None,
        )
    except (cdb.CollabError, sqlite3.Error) as error:
        st.error(str(error))
        return
    flash(f"Shared task “{title.strip()}” added.")
    st.rerun()


def page_plans() -> None:
    st.header("👥 Collaborative Plans")
    user = require_login()
    if user is None:
        return
    me = user["user_id"]

    with st.expander("➕ Create a new shared plan", expanded=not cdb.get_user_plans(me)):
        with st.form("create_plan_form", clear_on_submit=True):
            name = st.text_input("Plan name *", max_chars=100,
                                 placeholder="e.g. AIML Exam Preparation")
            description = st.text_area("Description")
            created = st.form_submit_button("Create plan", type="primary")
        if created:
            try:
                plan_id = cdb.create_plan(me, name, description)
            except (cdb.CollabError, sqlite3.Error) as error:
                st.error(str(error))
            else:
                st.session_state["collab_plan_id"] = plan_id  # open the new plan
                flash(f"Plan “{name.strip()}” created. You are the owner.")
                st.rerun()

    plans = cdb.get_user_plans(me)
    if not plans:
        st.info("You are not in any plan yet. Create one above, or accept an invitation.")
        return

    ids = [p["plan_id"] for p in plans]
    if st.session_state.get("collab_plan_id") not in ids:
        st.session_state["collab_plan_id"] = ids[0]
    by_id = {p["plan_id"]: p for p in plans}
    plan_id = st.selectbox(
        "Choose a plan", ids, key="collab_plan_id",
        format_func=lambda i: f"{by_id[i]['name']}  ({by_id[i]['role']})",
    )
    plan = by_id[plan_id]
    members = cdb.get_plan_members(plan_id)

    st.subheader(plan["name"])
    if plan.get("description"):
        st.caption(md_safe(plan["description"]))
    st.markdown(
        "👑 Owner: **" + md_safe(plan["owner_name"]) + "** · 👥 Members: "
        + ", ".join(md_safe(m["username"]) for m in members)
    )

    tab_tasks, tab_progress, tab_invite = st.tabs(["📋 Tasks", "📊 Progress", "✉️ Invite"])
    with tab_tasks:
        _render_add_task(plan_id, me, members)
        tasks = cdb.get_plan_tasks(plan_id)
        if not tasks:
            st.info("No shared tasks yet. Add the first one above.")
        for task in logic.sort_by_due_date(tasks):
            _render_plan_task(task, me, plan["owner_id"])
    with tab_progress:
        _render_progress(plan_id)
    with tab_invite:
        _render_invite(plan_id, me, members)


# --------------------------------------------------------------------------
# Share one personal task with a friend (used on task cards and after Add Task)
# --------------------------------------------------------------------------
def _send_share(task_id: int, me: int, other: int) -> None:
    _run(lambda: cdb.share_task(task_id, me, other), "Share request sent.")


def _stop_share(share_id: int, me: int) -> None:
    _run(lambda: cdb.revoke_task_share(share_id, me), "Sharing stopped.")


def render_share_panel(task_id: int, prefix: str) -> None:
    """Search a username and send a share request for `task_id`."""
    user = current_user()
    if user is None:
        return
    me = user["user_id"]
    st.markdown("**🤝 Share this task with a friend**")
    query = st.text_input(
        "Find a user by username", key=f"{prefix}_share_q_{task_id}",
        placeholder="Type a username…",
    )

    current = {s["recipient_id"]: s for s in cdb.get_task_shares(task_id)}
    if query.strip():
        results = cdb.search_users(query, exclude_user_id=me)
        if not results:
            st.warning("No user with that name.")
        for person in results:
            name_col, btn_col = st.columns([4, 1])
            name_col.markdown(f"**{md_safe(person['username'])}**")
            existing = current.get(person["user_id"])
            if existing:
                btn_col.caption("✅ Shared" if existing["status"] == "accepted" else "⏳ Requested")
            else:
                btn_col.button("Send request", key=f"{prefix}_send_{task_id}_{person['user_id']}",
                               type="primary", on_click=_send_share,
                               args=(task_id, me, person["user_id"]),
                               use_container_width=True)

    if current:
        st.caption("Currently shared with:")
        for sh in current.values():
            name_col, btn_col = st.columns([4, 1])
            state = "accepted" if sh["status"] == "accepted" else "waiting for them to accept"
            name_col.markdown(f"{md_safe(sh['username'])} · _{state}_")
            btn_col.button("Stop", key=f"{prefix}_stop_{sh['share_id']}",
                           on_click=_stop_share, args=(sh["share_id"], me),
                           use_container_width=True)
