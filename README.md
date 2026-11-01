# Smart Task Manager

A simple task-management web app built with **Python, Streamlit and SQLite**, developed with **GitHub Copilot** as the AI coding assistant.

Users can create tasks, set priorities and deadlines, track progress, and spot overdue work on one dashboard. Tasks are saved in a local SQLite database, so they are still there after the app is closed and reopened.

> GitHub Copilot is the *development* assistant. The app itself has no AI feature and needs no API key.

## Features

- **Add tasks** with title, description, category, priority (High / Medium / Low) and due date
- **Manage tasks**: edit, delete (with confirmation), start, mark done, reopen
- **Dashboard**: total, completed, pending and overdue counts, completion percentage, progress bar, high-priority tasks, recent tasks
- **Deadline tracking**: overdue, due today and due-soon tasks are highlighted; completed tasks are never counted as overdue
- **Search and filter**: search by title, filter by priority and status, sort by due date
- **Pages**: Dashboard, Add New Task, All Tasks, Upcoming & Overdue, Completed Tasks
- **Persistent storage** in SQLite, with parameterized SQL and `CHECK` constraints

### How the dashboard counts tasks

| Count | Meaning |
|---|---|
| Completed | status is Completed |
| Overdue | not completed **and** due date is before today |
| Pending | not completed and not overdue (Pending or In Progress) |

These three never overlap, so Completed + Pending + Overdue = Total.

## Setup (Windows, VS Code terminal)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Mac / Linux: activate with `source venv/bin/activate`.

## Run the app

```powershell
streamlit run app.py
```

Open the link shown in the terminal (usually http://localhost:8501). The database file `tasks.db` is created automatically on first run.

## Run the tests

```powershell
pytest -v
```

## Project structure

```
smart-task-manager/
├── app.py              # Streamlit UI only
├── database.py         # SQLite: create table, add, read, update, delete
├── task_logic.py       # Validation, deadlines, statistics, search/filter/sort
├── tests/
│   ├── test_database.py
│   └── test_task_logic.py
├── screenshots/        # Screenshots for the report
├── copilot-log.md      # Prompt log and review notes
├── requirements.txt
└── .github/copilot-instructions.md   # Project rules for Copilot
```

Architecture: **Streamlit (presentation) → task_logic.py (business logic) → database.py (SQLite)**.

## Database

Table `tasks`: `task_id` (auto primary key), `title`, `description`, `category`, `priority`, `status`, `due_date` (ISO `YYYY-MM-DD`), `created_at`.

Rules enforced in Python **and** in SQL: title not empty, priority in High/Medium/Low, status in Pending/In Progress/Completed. All queries use `?` placeholders.

## How GitHub Copilot was used

See [copilot-log.md](copilot-log.md) for the prompts, what Copilot produced, and what was changed or rejected after review. Copilot was used for code generation, explanation, debugging, refactoring, test generation, documentation and commit messages. Every suggestion was run and tested before being committed.

## Not in Version 1

Login, email notifications, AI chatbot, AI task suggestions, payments, mobile app, multi-user collaboration, cloud deployment.
