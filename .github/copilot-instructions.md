# Project: Smart Task Manager
Stack: Python, Streamlit, SQLite, pytest.

Rules:
- All SQL must be parameterized (use ? placeholders), never string concatenation.
- app.py = UI only. Database code goes in database.py. Validation/logic goes in task_logic.py.
- task_logic.py must not import streamlit or touch the database.
- Priority must be High, Medium or Low. Status must be Pending, In Progress or Completed.
- Dates are stored as ISO strings (YYYY-MM-DD). Past due dates are allowed (needed for overdue tasks).
- Keep functions small, use meaningful names, handle errors without crashing the app.
- Write pytest tests for business logic.
