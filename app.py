"""Smart Task Manager - Streamlit user interface.

This file is UI only:
  * database.py   -> saving and loading tasks (SQLite)
  * task_logic.py -> validation, deadlines, statistics, search/filter/sort
"""

import re
import sqlite3
from datetime import date

import streamlit as st

import collab_db
import collab_ui
import dashboard_html
import dashboard_ui
import database as db
import task_logic as logic

st.set_page_config(page_title="Smart Task Manager", page_icon="✅", layout="wide")
db.init_db()  # safe on every run: creates the table only if it is missing
collab_db.init_collab_db()  # Collaborative Planning tables (never touches existing data)

PAGES = [
    "Dashboard",
    "Add New Task",
    "All Tasks",
    "Upcoming & Overdue",
    "Completed Tasks",
    *collab_ui.COLLAB_PAGES,  # Collaborative Planning pages
]
PAGE_ICONS = {
    "Dashboard": "📊",
    "Add New Task": "➕",
    "All Tasks": "📋",
    "Upcoming & Overdue": "⏰",
    "Completed Tasks": "✅",
    **collab_ui.COLLAB_ICONS,
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
    "overdue": "red",
    "today": "orange",
    "soon": "orange",
    "later": "gray",
    "none": "gray",
    "completed": "green",
}
SORT_OPTIONS = ["Due date (earliest first)", "Due date (latest first)", "Newest added"]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def md_safe(text: object) -> str:
    """Escape Markdown characters so a title like '*x*' is shown literally."""
    return re.sub(r"([!-/:-@\[-`{-~])", r"\\\1", str(text or ""))


def flash(message: str, kind: str = "success") -> None:
    """Remember a message to show on the next run (after a button click)."""
    st.session_state["flash"] = (kind, message)


def show_flash() -> None:
    if "flash" in st.session_state:
        kind, message = st.session_state.pop("flash")
        getattr(st, kind)(message)


def go_to(page: str) -> None:
    st.session_state["page"] = page


# --------------------------------------------------------------------------
# Button callbacks (they run before the page reruns, so the UI is always fresh)
# --------------------------------------------------------------------------
def change_status(task_id: int, status: str) -> None:
    try:
        db.update_status(task_id, status)
        flash(f"Task marked as {status}.")
    except (ValueError, sqlite3.Error) as error:
        flash(f"Could not update the task: {error}", "error")


def start_edit(task_id: int) -> None:
    st.session_state["editing_id"] = task_id
    st.session_state.pop("confirm_delete_id", None)


def stop_edit() -> None:
    st.session_state.pop("editing_id", None)


def ask_delete(task_id: int) -> None:
    st.session_state["confirm_delete_id"] = task_id
    st.session_state.pop("editing_id", None)


def toggle_share(task_id: int) -> None:
    """Open or close the share panel of a task."""
    if st.session_state.get("sharing_id") == task_id:
        st.session_state.pop("sharing_id", None)
    else:
        st.session_state["sharing_id"] = task_id


def cancel_delete() -> None:
    st.session_state.pop("confirm_delete_id", None)


def confirm_delete(task_id: int) -> None:
    try:
        db.delete_task(task_id)
        flash("Task deleted.")
    except sqlite3.Error as error:
        flash(f"Could not delete the task: {error}", "error")
    st.session_state.pop("confirm_delete_id", None)


# --------------------------------------------------------------------------
# Task card
# --------------------------------------------------------------------------
def render_badges(task: dict) -> None:
    due = logic.parse_due_date(task["due_date"])
    state = logic.deadline_status(task)
    parts = [
        PRIORITY_BADGE.get(task["priority"], md_safe(task["priority"])),
        STATUS_BADGE.get(task["status"], md_safe(task["status"])),
    ]
    if task.get("category"):
        parts.append(f":violet-badge[{md_safe(task['category'])}]")
    if due:
        label = f"📅 {due:%d %b %Y} · {logic.deadline_label(task)}"
        if state == "completed":
            label = f"📅 {due:%d %b %Y}"
        parts.append(f":{DEADLINE_COLOR[state]}-badge[{label}]")
    st.markdown(" ".join(parts))


def render_edit_form(task: dict, section: str) -> None:
    task_id = task["task_id"]
    categories = list(logic.CATEGORIES)
    current_category = task.get("category") or "Other"
    if current_category not in categories:
        categories.append(current_category)

    with st.form(f"edit_form_{section}_{task_id}"):
        st.subheader("Edit task")
        title = st.text_input("Title", value=task["title"])
        description = st.text_area("Description", value=task.get("description") or "")
        col1, col2, col3 = st.columns(3)
        category = col1.selectbox(
            "Category", categories, index=categories.index(current_category)
        )
        priority = col2.selectbox(
            "Priority", logic.PRIORITIES, index=logic.PRIORITIES.index(task["priority"])
        )
        status = col3.selectbox(
            "Status", logic.STATUSES, index=logic.STATUSES.index(task["status"])
        )
        due = st.date_input(
            "Due date",
            value=logic.parse_due_date(task["due_date"]) or date.today(),
            format="DD/MM/YYYY",
        )
        save_col, cancel_col = st.columns(2)
        saved = save_col.form_submit_button(
            "💾 Save changes", type="primary", use_container_width=True
        )
        cancelled = cancel_col.form_submit_button("Cancel", use_container_width=True)

    if cancelled:
        stop_edit()
        st.rerun()
    if saved:
        errors = logic.validate_task(title, priority, due, status)
        if errors:
            for message in errors:
                st.error(message)
            return
        try:
            db.update_task(
                task_id, title, description, category, priority, status, due.isoformat()
            )
        except (ValueError, sqlite3.Error) as error:
            st.error(f"Could not save the task: {error}")
            return
        stop_edit()
        flash("Changes saved.")
        st.rerun()


def render_task_card(task: dict, section: str, actions: bool = True) -> None:
    """Draw one task. `section` keeps widget keys unique across pages."""
    task_id = task["task_id"]
    with st.container(border=True):
        if actions and st.session_state.get("editing_id") == task_id:
            render_edit_form(task, section)
            return

        st.markdown(f"**{md_safe(task['title'])}**")
        render_badges(task)
        if task.get("description"):
            st.caption(md_safe(task["description"]))
        if task.get("shared_by"):
            st.caption(f"🤝 Shared with you by **{md_safe(task['shared_by'])}**")
        elif task.get("shared_with"):
            st.caption("🤝 Shared with " + ", ".join(md_safe(n) for n in task["shared_with"]))

        if not actions:
            return

        if st.session_state.get("confirm_delete_id") == task_id:
            st.warning("Delete this task permanently?")
            yes_col, no_col, _ = st.columns([1, 1, 3])
            yes_col.button(
                "Yes, delete",
                key=f"{section}_yes_{task_id}",
                type="primary",
                on_click=confirm_delete,
                args=(task_id,),
                use_container_width=True,
            )
            no_col.button(
                "Cancel",
                key=f"{section}_no_{task_id}",
                on_click=cancel_delete,
                use_container_width=True,
            )
            return

        is_owner = not task.get("shared_by")  # shared-with-me tasks: status only
        cols = st.columns([1, 1, 1, 1, 1, 1])
        slot = 0
        if task["status"] == "Pending":
            cols[slot].button(
                "▶ Start",
                key=f"{section}_start_{task_id}",
                on_click=change_status,
                args=(task_id, "In Progress"),
                use_container_width=True,
            )
            slot += 1
        if task["status"] != "Completed":
            cols[slot].button(
                "✅ Done",
                key=f"{section}_done_{task_id}",
                on_click=change_status,
                args=(task_id, "Completed"),
                use_container_width=True,
            )
        else:
            cols[slot].button(
                "↩ Reopen",
                key=f"{section}_reopen_{task_id}",
                on_click=change_status,
                args=(task_id, "Pending"),
                use_container_width=True,
            )
        if is_owner:
            cols[2].button(
                "✏️ Edit",
                key=f"{section}_edit_{task_id}",
                on_click=start_edit,
                args=(task_id,),
                use_container_width=True,
            )
            cols[3].button(
                "🗑 Delete",
                key=f"{section}_delete_{task_id}",
                on_click=ask_delete,
                args=(task_id,),
                use_container_width=True,
            )
            cols[4].button(
                "🤝 Share",
                key=f"{section}_share_{task_id}",
                on_click=toggle_share,
                args=(task_id,),
                use_container_width=True,
            )
        if is_owner and st.session_state.get("sharing_id") == task_id:
            collab_ui.render_share_panel(task_id, section)


def render_task_list(tasks: list[dict], section: str, actions: bool = True) -> None:
    for task in tasks:
        render_task_card(task, section, actions)


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
def page_dashboard(tasks: list[dict]) -> None:
    st.header("📊 Dashboard")
    stats = logic.calculate_stats(tasks)

    cols = st.columns(5)
    cols[0].metric("Total tasks", stats["total"])
    cols[1].metric("Completed", stats["completed"])
    cols[2].metric("Pending", stats["pending"])
    cols[3].metric("Overdue", stats["overdue"])
    cols[4].metric("Completion", f"{stats['completion_percentage']}%")

    st.progress(
        stats["completion_percentage"] / 100,
        text=(
            f"Overall completion: {stats['completed']} of {stats['total']} tasks "
            f"({stats['completion_percentage']}%)"
        ),
    )

    if not tasks:
        st.info("No tasks yet. Add your first task to see the dashboard come alive.")
        st.button("➕ Add your first task", on_click=go_to, args=("Add New Task",))
        return

    urgent = [
        t for t in tasks if t["priority"] == "High" and not logic.is_completed(t)
    ]
    if urgent:
        st.subheader("🔴 High-priority tasks to finish")
        render_task_list(logic.sort_by_due_date(urgent)[:3], "dash_high", actions=False)

    st.subheader("🕒 Recent tasks")
    recent = sorted(tasks, key=lambda t: t["task_id"], reverse=True)[:5]
    render_task_list(recent, "dash_recent", actions=False)


def page_add_task() -> None:
    st.header("➕ Add New Task")
    version = st.session_state.get("add_form_version", 0)  # new number = blank form

    last_id = st.session_state.get("last_added_id")
    if last_id:  # offer to share the task that was just created
        with st.container(border=True):
            collab_ui.render_share_panel(last_id, "add")
            st.button("Done", key="add_share_done",
                      on_click=lambda: st.session_state.pop("last_added_id", None))

    with st.form("add_task_form"):
        title = st.text_input("Title *", key=f"add_title_{version}", max_chars=100)
        description = st.text_area("Description", key=f"add_desc_{version}")
        col1, col2, col3 = st.columns(3)
        category = col1.selectbox(
            "Category", logic.CATEGORIES, key=f"add_cat_{version}"
        )
        priority = col2.selectbox(
            "Priority", logic.PRIORITIES, index=1, key=f"add_pri_{version}"
        )
        due = col3.date_input(
            "Due date",
            value=date.today(),
            format="DD/MM/YYYY",
            key=f"add_due_{version}",
            help="Past dates are allowed. An unfinished task past its date shows as overdue.",
        )
        submitted = st.form_submit_button("Add task", type="primary")

    if not submitted:
        return

    errors = logic.validate_task(title, priority, due)
    if errors:
        for message in errors:
            st.error(message)
        return
    try:
        new_id = db.add_task(
            title, description, category, priority, "Pending", due.isoformat(),
            owner_id=collab_ui.current_user()["user_id"],
        )
    except (ValueError, sqlite3.Error) as error:
        st.error(f"Could not save the task: {error}")
        return

    st.session_state["add_form_version"] = version + 1
    st.session_state["last_added_id"] = new_id
    flash(f"Task “{title.strip()}” added. You can share it below.")
    st.rerun()


def page_all_tasks(tasks: list[dict]) -> None:
    st.header("📋 All Tasks")
    if not tasks:
        st.info("No tasks yet. Use “Add New Task” in the sidebar.")
        return

    col1, col2, col3, col4 = st.columns([3, 1.5, 1.5, 2])
    search = col1.text_input("🔍 Search by title", placeholder="Type to search…")
    priority = col2.selectbox("Priority", ["All", *logic.PRIORITIES])
    status = col3.selectbox("Status", ["All", *logic.STATUSES])
    sort_choice = col4.selectbox("Sort by", SORT_OPTIONS)

    shown = logic.filter_tasks(tasks, search, priority, status)
    if sort_choice == SORT_OPTIONS[0]:
        shown = logic.sort_by_due_date(shown)
    elif sort_choice == SORT_OPTIONS[1]:
        shown = logic.sort_by_due_date(shown, descending=True)
    else:
        shown = sorted(shown, key=lambda t: t["task_id"], reverse=True)

    st.caption(f"Showing {len(shown)} of {len(tasks)} tasks")
    if not shown:
        st.warning("No tasks match your search or filters.")
    render_task_list(shown, "all")


def page_upcoming(tasks: list[dict]) -> None:
    st.header("⏰ Upcoming & Overdue")
    groups = logic.group_by_deadline(tasks)

    st.subheader(f"⚠️ Overdue ({len(groups['overdue'])})")
    if groups["overdue"]:
        render_task_list(groups["overdue"], "up_over")
    else:
        st.success("Nothing overdue. Nice work!")

    st.subheader(f"📅 Due in the next {logic.UPCOMING_DAYS} days ({len(groups['due_soon'])})")
    if groups["due_soon"]:
        render_task_list(groups["due_soon"], "up_soon")
    else:
        st.info("No deadlines coming up this week.")

    st.subheader(f"🗓 Later ({len(groups['later'])})")
    if groups["later"]:
        render_task_list(groups["later"], "up_later")
    else:
        st.caption("No later tasks.")


def page_completed(tasks: list[dict]) -> None:
    st.header("✅ Completed Tasks")
    done = [t for t in tasks if logic.is_completed(t)]
    if not done:
        st.info("No completed tasks yet.")
        return
    st.caption(f"{len(done)} completed")
    render_task_list(sorted(done, key=lambda t: t["task_id"], reverse=True), "done")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    dashboard_ui.inject_theme()  # dark purple theme for every page
    user = collab_ui.current_user()
    if user is None:  # not logged in: the login screen is the first thing shown
        show_flash()
        collab_ui.page_auth()
        return

    tasks = collab_db.get_user_tasks(user["user_id"])  # my tasks + tasks shared with me
    stats = logic.calculate_stats(tasks)

    with st.sidebar:
        st.markdown(dashboard_html.brand_html(), unsafe_allow_html=True)
        dashboard_ui.render_nav(
            PAGES, PAGE_ICONS,
            badges={"Invitations": collab_db.count_pending_requests(user["user_id"])},
        )
        st.divider()
        st.caption(
            f"{stats['total']} tasks · {stats['completed']} done · "
            f"{stats['overdue']} overdue"
        )
        collab_ui.render_sidebar_account()

    show_flash()
    page = st.session_state["page"]
    if page == "Dashboard":
        dashboard_ui.render_dashboard(tasks)  # new interactive dashboard
    elif page == "Add New Task":
        page_add_task()
    elif page == "All Tasks":
        page_all_tasks(tasks)
    elif page == "Upcoming & Overdue":
        page_upcoming(tasks)
    elif page == "Completed Tasks":
        page_completed(tasks)
    elif page == "People":
        collab_ui.page_people()
    elif page == "Collaborative Plans":
        collab_ui.page_plans()
    else:
        collab_ui.page_invitations()


if "page" not in st.session_state:
    st.session_state["page"] = "Dashboard"
main()
