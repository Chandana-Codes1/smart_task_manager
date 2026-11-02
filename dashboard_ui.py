"""Interactive dashboard page (dark purple theme).

Interactive parts:
  * search bar for tasks, plans and people
  * clickable stat cards that filter the Recent Tasks list (and a filter control)
  * tick a task's checkbox to complete it; the ⋮ menu has Start/Done/Edit/Share/Delete
  * month calendar: previous/next month, dots on days with tasks, click a day to see its tasks
  * upcoming deadlines, collaborative plans (open with ›), quick buttons
  * bell with pending requests (accept/reject right there) and an account menu

This file only draws things; saving goes through database.py / collab_db.py,
and HTML/CSS strings come from dashboard_html.py.
"""

import calendar
import sqlite3
from datetime import date

import streamlit as st

import collab_db as cdb
import collab_ui
import dashboard_html as H
import database as db
import task_logic as logic

FILTERS = ["All", "Pending", "Completed", "Overdue"]
RECENT_LIMIT = 5


def render_nav(pages: list[str], icons: dict, badges: dict | None = None) -> None:
    """Sidebar menu: one clickable button per page, the current page highlighted."""
    current = st.session_state.get("page")
    for name in pages:
        count = (badges or {}).get(name)
        label = f"{icons.get(name, '•')}  {name}" + (f"   ({count})" if count else "")
        with st.container(key=f"nav_{name.replace(' ', '_').replace('&', 'and')}"):
            st.button(label, key=f"navbtn_{name}", on_click=_goto, args=(name,),
                      type="primary" if name == current else "secondary",
                      use_container_width=True)


def inject_theme() -> None:
    st.markdown(H.THEME_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Callbacks (run before the page reruns, like the ones in app.py)
# --------------------------------------------------------------------------
def _flash(message: str, kind: str = "success") -> None:
    st.session_state["flash"] = (kind, message)


def _goto(page: str) -> None:
    st.session_state["page"] = page


def _set_filter(name: str) -> None:
    st.session_state["dash_filter"] = name


def _set_status(task_id: int, status: str) -> None:
    try:
        db.update_status(task_id, status)
        _flash(f"Task marked as {status}.")
    except (ValueError, sqlite3.Error) as error:
        _flash(f"Could not update the task: {error}", "error")


def _toggle_done(task_id: int, key: str) -> None:
    _set_status(task_id, "Completed" if st.session_state.get(key) else "Pending")


def _edit(task_id: int) -> None:
    st.session_state["editing_id"] = task_id
    st.session_state.pop("confirm_delete_id", None)
    _goto("All Tasks")


def _delete(task_id: int) -> None:
    st.session_state["confirm_delete_id"] = task_id
    st.session_state.pop("editing_id", None)
    _goto("All Tasks")


def _share(task_id: int) -> None:
    st.session_state["sharing_id"] = task_id
    _goto("All Tasks")


def _open_plan(plan_id: int) -> None:
    st.session_state["collab_plan_id"] = plan_id
    _goto("Collaborative Plans")


def _clear_search() -> None:
    st.session_state["dash_search"] = ""


def _next_quote() -> None:
    st.session_state["quote_i"] = (st.session_state.get("quote_i", 0) + 1) % len(H.QUOTES)


def _cal_shift(delta: int) -> None:
    month = st.session_state["cal_m"] + delta
    year = st.session_state["cal_y"]
    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1
    st.session_state["cal_m"], st.session_state["cal_y"] = month, year


def _cal_today() -> None:
    today = date.today()
    st.session_state.update(cal_y=today.year, cal_m=today.month, cal_sel=today.isoformat())


def _cal_pick(iso: str) -> None:
    st.session_state["cal_sel"] = iso


# --------------------------------------------------------------------------
# Small building blocks
# --------------------------------------------------------------------------
def _is_owner(task: dict) -> bool:
    return not task.get("shared_by")


def _task_row(task: dict) -> None:
    """One task: checkbox + details + ⋮ menu."""
    task_id = task["task_id"]
    done = task["status"] == "Completed"
    with st.container(key=f"trow_{task_id}"):
        check_col, body_col, menu_col = st.columns([0.07, 0.83, 0.1], vertical_alignment="center")
        key = f"dash_chk_{task_id}_{task['status']}"  # status in the key keeps the box in sync
        check_col.checkbox(
            "Mark done", value=done, key=key, label_visibility="collapsed",
            on_change=_toggle_done, args=(task_id, key),
        )
        body_col.markdown(H.task_row_html(task), unsafe_allow_html=True)
        with menu_col.popover("⋮"):
            if task["status"] == "Pending":
                st.button("▶ Start", key=f"d_start_{task_id}", on_click=_set_status,
                          args=(task_id, "In Progress"), use_container_width=True)
            if not done:
                st.button("✅ Mark done", key=f"d_done_{task_id}", on_click=_set_status,
                          args=(task_id, "Completed"), use_container_width=True)
            else:
                st.button("↩ Reopen", key=f"d_reopen_{task_id}", on_click=_set_status,
                          args=(task_id, "Pending"), use_container_width=True)
            if _is_owner(task):
                st.button("✏️ Edit", key=f"d_edit_{task_id}", on_click=_edit,
                          args=(task_id,), use_container_width=True)
                st.button("🤝 Share", key=f"d_share_{task_id}", on_click=_share,
                          args=(task_id,), use_container_width=True)
                st.button("🗑 Delete", key=f"d_del_{task_id}", on_click=_delete,
                          args=(task_id,), use_container_width=True)


def _filtered(tasks: list[dict], name: str) -> list[dict]:
    if name == "Completed":
        rows = [t for t in tasks if logic.is_completed(t)]
    elif name == "Overdue":
        rows = [t for t in tasks if logic.is_overdue(t)]
    elif name == "Pending":
        rows = [t for t in tasks if not logic.is_completed(t) and not logic.is_overdue(t)]
    else:
        return sorted(tasks, key=lambda t: t["task_id"], reverse=True)
    return logic.sort_by_due_date(rows)


# --------------------------------------------------------------------------
# Top bar: title, search, bell, account
# --------------------------------------------------------------------------
def _notifications(user: dict) -> None:
    me = user["user_id"]
    shares = cdb.get_pending_task_shares(me)
    invites = cdb.get_pending_invitations(me)
    if not shares and not invites:
        st.caption("No new notifications 🎉")
        return
    for sh in shares:
        st.markdown(f"**{collab_ui.md_safe(sh['owner_name'])}** shared the task "
                    f"**{collab_ui.md_safe(sh['task_title'])}**")
        a, b = st.columns(2)
        a.button("Accept", key=f"nb_sa_{sh['share_id']}", type="primary",
                 on_click=collab_ui._answer_share, args=(sh["share_id"], me, True),
                 use_container_width=True)
        b.button("Reject", key=f"nb_sr_{sh['share_id']}",
                 on_click=collab_ui._answer_share, args=(sh["share_id"], me, False),
                 use_container_width=True)
    for inv in invites:
        st.markdown(f"**{collab_ui.md_safe(inv['inviter_name'])}** invited you to "
                    f"**{collab_ui.md_safe(inv['plan_name'])}**")
        a, b = st.columns(2)
        a.button("Accept", key=f"nb_ia_{inv['invitation_id']}", type="primary",
                 on_click=collab_ui._answer, args=(inv["invitation_id"], me, True),
                 use_container_width=True)
        b.button("Reject", key=f"nb_ir_{inv['invitation_id']}",
                 on_click=collab_ui._answer, args=(inv["invitation_id"], me, False),
                 use_container_width=True)


def _top_bar(user: dict) -> None:
    with st.container(key="topbar"):
        title_col, search_col, bell_col, user_col = st.columns(
            [3, 4, 0.8, 1.6], vertical_alignment="center"
        )
        title_col.markdown(H.page_title_html("Dashboard", "Plan • Track • Collaborate • Achieve"),
                           unsafe_allow_html=True)
        search_col.text_input("Search", key="dash_search", label_visibility="collapsed",
                              placeholder="🔍  Search tasks, plans or people…")
        count = cdb.count_pending_requests(user["user_id"])
        with bell_col.popover(f"🔔 {count}" if count else "🔔", use_container_width=True):
            _notifications(user)
        with user_col.popover(f"👤 {user['username']}", use_container_width=True):
            st.caption(user["email"])
            st.button("🤝 My people", key="menu_people", on_click=_goto, args=("People",),
                      use_container_width=True)
            st.button("Log out", key="menu_logout", on_click=collab_ui.logout,
                      use_container_width=True)


def _search_results(user: dict, tasks: list[dict]) -> None:
    query = st.session_state.get("dash_search", "").strip()
    if not query:
        return
    me = user["user_id"]
    with st.container(key="card_search"):
        head, clear = st.columns([5, 1], vertical_alignment="center")
        head.markdown(f'<div class="card-h">🔍 Results for “{H.escape(query)}”</div>',
                      unsafe_allow_html=True)
        clear.button("✖ Clear", key="search_clear", on_click=_clear_search,
                     use_container_width=True)

        found_tasks = logic.filter_tasks(tasks, query)[:6]
        plans = [p for p in cdb.get_user_plans(me) if query.lower() in p["name"].lower()][:4]
        people = cdb.search_users(query, exclude_user_id=me)[:5]
        if not (found_tasks or plans or people):
            st.info("Nothing matches your search.")
        if found_tasks:
            st.markdown("**Tasks**")
            for task in found_tasks:
                st.markdown(H.task_row_html(task), unsafe_allow_html=True)
        if plans:
            st.markdown("**Plans**")
            for plan in plans:
                name_col, btn_col = st.columns([5, 1], vertical_alignment="center")
                name_col.markdown(f"👥 {collab_ui.md_safe(plan['name'])}")
                btn_col.button("Open", key=f"sr_plan_{plan['plan_id']}", on_click=_open_plan,
                               args=(plan["plan_id"],), use_container_width=True)
        if people:
            st.markdown("**People**")
            for person in people:
                name_col, btn_col = st.columns([5, 1], vertical_alignment="center")
                name_col.markdown(f"🙂 {collab_ui.md_safe(person['username'])}")
                if cdb.is_following(me, person["user_id"]):
                    btn_col.caption("Following")
                else:
                    btn_col.button("Follow", key=f"sr_fol_{person['user_id']}",
                                   on_click=collab_ui._follow, args=(me, person["user_id"]),
                                   use_container_width=True)


# --------------------------------------------------------------------------
# Main column
# --------------------------------------------------------------------------
def _hero(user: dict, stats: dict) -> None:
    with st.container(key="hero"):
        quote = H.QUOTES[st.session_state.get("quote_i", date.today().toordinal()) % len(H.QUOTES)]
        st.markdown(H.hero_html(user["username"], stats, quote), unsafe_allow_html=True)
        _, quote_col = st.columns([5, 1.3])
        quote_col.button("↻ New quote", key="quote_btn", on_click=_next_quote,
                         use_container_width=True)


def _stat_cards(stats: dict) -> None:
    targets = {"total": "All", "completed": "Completed", "pending": "Pending", "overdue": "Overdue"}
    for col, (kind, flt) in zip(st.columns(4), targets.items()):
        with col, st.container(key=f"stat_{kind}"):
            st.markdown(H.stat_html(kind, stats[kind]), unsafe_allow_html=True)
            st.button(f"Show {kind}", key=f"stat_btn_{kind}", on_click=_set_filter, args=(flt,))


def _progress_card(stats: dict) -> None:
    with st.container(key="card_progress"):
        st.markdown('<div class="card-h">🎯 Overall Progress</div>', unsafe_allow_html=True)
        st.markdown(H.donut_html(stats), unsafe_allow_html=True)


def _recent_card(tasks: list[dict]) -> None:
    with st.container(key="card_recent"):
        head, view_all = st.columns([3, 1.2], vertical_alignment="center")
        head.markdown('<div class="card-h">📋 Recent Tasks</div>', unsafe_allow_html=True)
        view_all.button("View All →", key="view_all", on_click=_goto, args=("All Tasks",),
                        use_container_width=True)
        st.segmented_control("Filter", FILTERS, key="dash_filter", label_visibility="collapsed")
        chosen = st.session_state.get("dash_filter") or "All"
        rows = _filtered(tasks, chosen)
        if not tasks:
            st.info("No tasks yet. Add your first task to see the dashboard come alive.")
        elif not rows:
            st.success(f"No {chosen.lower()} tasks. 🎉" if chosen != "All" else "Nothing here.")
        else:
            shown = rows[:RECENT_LIMIT]
            st.markdown(H.priority_edge_css(shown), unsafe_allow_html=True)
            for task in shown:
                _task_row(task)
            if len(rows) > len(shown):
                st.caption(f"Showing {len(shown)} of {len(rows)} — use View All to see the rest.")


def _cta() -> None:
    with st.container(key="cta"):
        text_col, add_col, plan_col = st.columns([3, 1.1, 1.1], vertical_alignment="center")
        text_col.markdown(H.cta_html(), unsafe_allow_html=True)
        add_col.button("＋ Add New Task", key="cta_add", type="primary", on_click=_goto,
                       args=("Add New Task",), use_container_width=True)
        plan_col.button("👥 Create Plan", key="cta_plan", on_click=_goto,
                        args=("Collaborative Plans",), use_container_width=True)


# --------------------------------------------------------------------------
# Right column: calendar, upcoming deadlines, plans
# --------------------------------------------------------------------------
def _calendar_card(tasks: list[dict]) -> None:
    today = date.today()
    for key, value in (("cal_y", today.year), ("cal_m", today.month), ("cal_sel", today.isoformat())):
        st.session_state.setdefault(key, value)
    year, month = st.session_state["cal_y"], st.session_state["cal_m"]

    by_day: dict[str, list[dict]] = {}
    for task in tasks:
        due = logic.parse_due_date(task.get("due_date"))
        if due:
            by_day.setdefault(due.isoformat(), []).append(task)
    day_state = {}
    for iso, items in by_day.items():
        if any(logic.is_overdue(t) for t in items):
            day_state[iso] = "overdue"
        elif any(not logic.is_completed(t) for t in items):
            day_state[iso] = "pending"
        else:
            day_state[iso] = "done"
    st.markdown(H.calendar_dots_css(day_state, today.isoformat()), unsafe_allow_html=True)

    with st.container(key="card_calendar"):
        with st.container(key="calhead"):
            title, prev_col, today_col, next_col = st.columns([3, 1, 1.3, 1], vertical_alignment="center")
            title.markdown(f'<div class="cal-title">🗓 {calendar.month_name[month]} {year}</div>',
                           unsafe_allow_html=True)
            prev_col.button("‹", key="cal_prev", on_click=_cal_shift, args=(-1,), use_container_width=True)
            today_col.button("Today", key="cal_today", on_click=_cal_today, use_container_width=True)
            next_col.button("›", key="cal_next", on_click=_cal_shift, args=(1,), use_container_width=True)

        with st.container(key="calwrap"):
            st.markdown('<div class="cal-wd">' + "".join(f"<span>{d}</span>" for d in
                        ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")) + "</div>",
                        unsafe_allow_html=True)
            selected = st.session_state["cal_sel"]
            for week in calendar.Calendar(firstweekday=6).monthdatescalendar(year, month):
                for col, day in zip(st.columns(7, gap="small"), week):
                    if day.month != month:
                        col.write("")
                        continue
                    iso = day.isoformat()
                    col.button(str(day.day), key=f"cal_{iso}", on_click=_cal_pick, args=(iso,),
                               type="primary" if iso == selected else "secondary",
                               use_container_width=True)

        picked = date.fromisoformat(selected)
        items = by_day.get(selected, [])
        st.markdown(f"**{picked:%A, %d %b %Y}**" + (f" · {len(items)} due" if items else ""))
        if items:
            for task in items:
                st.markdown(H.task_row_html(task), unsafe_allow_html=True)
        else:
            st.caption("Nothing due on this day.")
            st.button("＋ Add a task", key="cal_add", on_click=_goto, args=("Add New Task",))


def _deadlines_card(tasks: list[dict]) -> None:
    soon = [
        t for t in tasks
        if not logic.is_completed(t)
        and (logic.days_until_due(t) is not None and logic.days_until_due(t) <= logic.UPCOMING_DAYS)
    ]
    soon = logic.sort_by_due_date(soon)[:5]
    with st.container(key="card_deadlines"):
        st.markdown('<div class="card-h">⏰ Upcoming Deadlines</div>', unsafe_allow_html=True)
        if soon:
            st.markdown("".join(H.deadline_row_html(t) for t in soon), unsafe_allow_html=True)
        else:
            st.caption("No deadlines in the next 7 days. 🎉")


def _plans_card(user: dict) -> None:
    plans = cdb.get_user_plans(user["user_id"])[:4]
    with st.container(key="card_plans"):
        st.markdown('<div class="card-h">👥 Collaborative Plans</div>', unsafe_allow_html=True)
        if not plans:
            st.caption("No plans yet. Create one and invite friends.")
        for plan in plans:
            members = cdb.get_plan_members(plan["plan_id"])
            pct = cdb.plan_progress(plan["plan_id"])["completion_percentage"]
            body, go = st.columns([6, 1], vertical_alignment="center")
            body.markdown(H.plan_row_html(plan, len(members), pct), unsafe_allow_html=True)
            go.button("›", key=f"plan_go_{plan['plan_id']}", on_click=_open_plan,
                      args=(plan["plan_id"],), use_container_width=True)


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
def render_dashboard(tasks: list[dict]) -> None:
    user = collab_ui.current_user()
    if user is None:
        return
    st.session_state.setdefault("dash_filter", "All")
    stats = logic.calculate_stats(tasks)

    _top_bar(user)
    _search_results(user, tasks)

    main_col, side_col = st.columns([2.9, 1.15], gap="large")
    with main_col:
        _hero(user, stats)
        _stat_cards(stats)

        ranked_tasks = logic.rank_tasks_by_smart_priority(tasks)

        if ranked_tasks:
            st.markdown("### 🧠 Smart Recommended Tasks")
            for item in ranked_tasks[:5]:
                task = item["task"]
                with st.container(border=True):
                    st.markdown(f"**{task['title']}**")
                    st.caption(f"Smart Priority Score: {item['score']}/100")
                    st.info(f"Reason: {item['reason']}")

        progress_col, recent_col = st.columns([1, 1.55], gap="medium")
        with progress_col:
            _progress_card(stats)
        with recent_col:
            _recent_card(tasks)
        _cta()
    with side_col:
        _calendar_card(tasks)
        _deadlines_card(tasks)
        _plans_card(user)
