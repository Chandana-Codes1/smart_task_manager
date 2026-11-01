"""Unit tests for task_logic.py (pure functions, no database needed)."""

from datetime import date, datetime

import pytest

import task_logic as logic

TODAY = date(2026, 10, 31)


def make_task(title="Task", priority="Medium", status="Pending", due="2026-11-05", task_id=1):
    return {
        "task_id": task_id,
        "title": title,
        "priority": priority,
        "status": status,
        "due_date": due,
        "category": "Academic",
        "description": "",
    }


# ---------------------------------------------------------------- validation
def test_valid_task_has_no_errors():
    assert logic.validate_task("Write report", "High", date(2026, 11, 5)) == []


@pytest.mark.parametrize("title", ["", "   ", None, 123])
def test_empty_or_non_text_title_is_rejected(title):
    errors = logic.validate_task(title, "High", date(2026, 11, 5))
    assert "Title cannot be empty." in errors


def test_too_long_title_is_rejected():
    errors = logic.validate_task("x" * 101, "High", date(2026, 11, 5))
    assert any("at most" in e for e in errors)


@pytest.mark.parametrize("priority", ["Urgent", "high", "", None])
def test_invalid_priority_is_rejected(priority):
    errors = logic.validate_task("Task", priority, date(2026, 11, 5))
    assert "Priority must be High, Medium or Low." in errors


def test_invalid_status_is_rejected():
    errors = logic.validate_task("Task", "High", date(2026, 11, 5), status="Blocked")
    assert any("Status" in e for e in errors)


@pytest.mark.parametrize("due", [None, "2026-11-05", datetime(2026, 11, 5, 9, 0)])
def test_invalid_due_date_is_rejected(due):
    errors = logic.validate_task("Task", "High", due)
    assert "Please choose a valid due date." in errors


def test_past_due_date_is_allowed():
    assert logic.validate_task("Old task", "Low", date(2020, 1, 1)) == []


def test_several_problems_are_all_reported():
    assert len(logic.validate_task("", "Nope", None)) == 3


# ------------------------------------------------------------------- parsing
def test_parse_due_date_accepts_iso_string_and_date():
    assert logic.parse_due_date("2026-11-05") == date(2026, 11, 5)
    assert logic.parse_due_date(date(2026, 11, 5)) == date(2026, 11, 5)


@pytest.mark.parametrize("value", [None, "", "05/11/2026", "2026-13-40", 5])
def test_parse_due_date_returns_none_for_bad_values(value):
    assert logic.parse_due_date(value) is None


# ------------------------------------------------------------------- overdue
def test_incomplete_task_in_the_past_is_overdue():
    assert logic.is_overdue(make_task(due="2026-10-30"), TODAY)


def test_task_due_today_is_not_overdue():
    task = make_task(due="2026-10-31")
    assert not logic.is_overdue(task, TODAY)
    assert logic.deadline_status(task, TODAY) == "today"
    assert logic.deadline_label(task, TODAY) == "Due today"


def test_completed_past_task_is_not_overdue():
    task = make_task(status="Completed", due="2020-01-01")
    assert not logic.is_overdue(task, TODAY)
    assert logic.deadline_status(task, TODAY) == "completed"


def test_in_progress_past_task_is_overdue():
    assert logic.is_overdue(make_task(status="In Progress", due="2026-10-01"), TODAY)


def test_task_without_due_date_is_never_overdue():
    task = make_task(due=None)
    assert not logic.is_overdue(task, TODAY)
    assert logic.deadline_label(task, TODAY) == "No due date"


@pytest.mark.parametrize(
    ("due", "expected"),
    [
        ("2026-10-30", "Overdue by 1 day"),
        ("2026-10-28", "Overdue by 3 days"),
        ("2026-10-31", "Due today"),
        ("2026-11-01", "Due in 1 day"),
        ("2026-11-10", "Due in 10 days"),
    ],
)
def test_deadline_label_text(due, expected):
    assert logic.deadline_label(make_task(due=due), TODAY) == expected


def test_due_soon_window():
    assert logic.is_due_soon(make_task(due="2026-10-31"), TODAY)   # today
    assert logic.is_due_soon(make_task(due="2026-11-03"), TODAY)   # +3 days
    assert not logic.is_due_soon(make_task(due="2026-11-04"), TODAY)
    assert not logic.is_due_soon(make_task(due="2026-10-30"), TODAY)  # overdue, not "soon"
    assert not logic.is_due_soon(make_task(status="Completed", due="2026-11-01"), TODAY)


# --------------------------------------------------------------------- stats
def test_stats_for_empty_list():
    stats = logic.calculate_stats([], TODAY)
    assert stats == {
        "total": 0,
        "completed": 0,
        "pending": 0,
        "overdue": 0,
        "completion_percentage": 0.0,
    }


def test_stats_match_blueprint_example():
    # 12 tasks: 5 completed, 6 pending, 1 overdue -> 41.7 %
    tasks = (
        [make_task(status="Completed", due="2026-10-01") for _ in range(5)]
        + [make_task(due="2026-12-01") for _ in range(5)]
        + [make_task(status="In Progress", due="2026-12-01")]
        + [make_task(due="2026-10-20")]
    )
    stats = logic.calculate_stats(tasks, TODAY)
    assert stats["total"] == 12
    assert stats["completed"] == 5
    assert stats["pending"] == 6
    assert stats["overdue"] == 1
    assert stats["completion_percentage"] == 41.7


def test_stats_groups_always_add_up_to_total():
    tasks = [
        make_task(due="2026-10-01"),
        make_task(status="Completed", due="2026-10-01"),
        make_task(due="2026-11-30"),
        make_task(due=None),
    ]
    s = logic.calculate_stats(tasks, TODAY)
    assert s["completed"] + s["pending"] + s["overdue"] == s["total"]


def test_all_completed_is_100_percent():
    tasks = [make_task(status="Completed") for _ in range(3)]
    assert logic.calculate_stats(tasks, TODAY)["completion_percentage"] == 100.0


# ----------------------------------------------------------- search / filter
@pytest.fixture
def sample_tasks():
    return [
        make_task("Physics homework", "High", "Pending", "2026-11-02", 1),
        make_task("Walk the dog", "Low", "Completed", "2026-10-26", 2),
        make_task("Prepare PHYSICS lab", "Medium", "In Progress", "2026-11-10", 3),
        make_task("Buy groceries", "Low", "Pending", None, 4),
    ]


def test_search_is_case_insensitive_and_matches_title(sample_tasks):
    result = logic.filter_tasks(sample_tasks, search="physics")
    assert [t["task_id"] for t in result] == [1, 3]


def test_search_with_no_match_returns_empty(sample_tasks):
    assert logic.filter_tasks(sample_tasks, search="zzz") == []


def test_blank_search_returns_everything(sample_tasks):
    assert len(logic.filter_tasks(sample_tasks, search="   ")) == 4


def test_filter_by_priority(sample_tasks):
    result = logic.filter_tasks(sample_tasks, priority="Low")
    assert [t["task_id"] for t in result] == [2, 4]


def test_filter_by_status(sample_tasks):
    result = logic.filter_tasks(sample_tasks, status="Completed")
    assert [t["task_id"] for t in result] == [2]


def test_filters_combine(sample_tasks):
    result = logic.filter_tasks(sample_tasks, search="physics", status="Pending")
    assert [t["task_id"] for t in result] == [1]


# --------------------------------------------------------------------- sort
def test_sort_by_due_date_ascending_puts_undated_last(sample_tasks):
    ids = [t["task_id"] for t in logic.sort_by_due_date(sample_tasks)]
    assert ids == [2, 1, 3, 4]


def test_sort_by_due_date_descending_still_puts_undated_last(sample_tasks):
    ids = [t["task_id"] for t in logic.sort_by_due_date(sample_tasks, descending=True)]
    assert ids == [3, 1, 2, 4]


# ------------------------------------------------------------------ grouping
def test_group_by_deadline_ignores_completed_and_splits_rest(sample_tasks):
    groups = logic.group_by_deadline(sample_tasks, TODAY)
    assert [t["task_id"] for t in groups["overdue"]] == []          # task 2 is completed
    assert [t["task_id"] for t in groups["due_soon"]] == [1]        # Nov 2 (2 days)
    assert [t["task_id"] for t in groups["later"]] == [3, 4]        # Nov 10 + no date


def test_group_by_deadline_finds_overdue():
    groups = logic.group_by_deadline([make_task(due="2026-10-20")], TODAY)
    assert len(groups["overdue"]) == 1



# ------------------------------------------------------ smart prioritisation

def test_smart_score_rewards_high_priority():
    task = make_task(priority="High", due=None)
    assert logic.calculate_smart_score(task, TODAY) == 50


def test_smart_score_rewards_urgent_deadline():
    task = make_task(priority="Medium", due="2026-10-31")
    assert logic.calculate_smart_score(task, TODAY) == 70


def test_smart_score_rewards_overdue_tasks():
    task = make_task(priority="High", due="2026-10-30")
    assert logic.calculate_smart_score(task, TODAY) == 100


def test_completed_tasks_are_excluded_from_ranking():
    tasks = [
        make_task("Active task", "High", "Pending", "2026-11-05", 1),
        make_task("Finished task", "High", "Completed", "2026-10-30", 2),
    ]

    ranked = logic.rank_tasks_by_smart_priority(tasks, TODAY)

    assert len(ranked) == 1
    assert ranked[0]["task"]["task_id"] == 1


def test_smart_ranking_places_overdue_task_first():
    tasks = [
        make_task("Future task", "High", "Pending", "2026-11-10", 1),
        make_task("Overdue task", "Low", "Pending", "2026-10-30", 2),
    ]

    ranked = logic.rank_tasks_by_smart_priority(tasks, TODAY)

    assert ranked[0]["task"]["task_id"] == 2
    assert ranked[0]["reason"] == "Overdue by 1 day(s)"
