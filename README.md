# Expense Tracker — Flask + SQLite Backend

## Folder Structure
```
backend/
├── app.py           ← Flask REST API
├── index.html       ← Frontend (connects to API)
├── requirements.txt ← Python dependencies
└── expenses.db      ← Auto-created on first run
```

## Setup & Run

### Step 1 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 2 — Start the Flask server
```bash
python app.py
```
Server starts at: http://localhost:5000

### Step 3 — Open the frontend
Open `index.html` in your browser (double-click or use Live Server in VS Code).

---

## API Endpoints

| Method | Endpoint              | Description              |
|--------|-----------------------|--------------------------|
| GET    | /api/health           | Check server status      |
| GET    | /api/expenses         | Get all expenses         |
| POST   | /api/expenses         | Add new expense          |
| PUT    | /api/expenses/:id     | Update expense           |
| DELETE | /api/expenses/:id     | Delete expense           |
| GET    | /api/summary          | Stats + category totals  |
| GET    | /api/budgets          | Get budgets + usage      |
| POST   | /api/budgets          | Set/update a budget      |
| DELETE | /api/budgets/:id      | Remove a budget          |

## Query Filters (GET /api/expenses)
- `?month=2025-06` — Filter by month
- `?category=Food` — Filter by category
- `?limit=50&offset=0` — Pagination

## Example POST /api/expenses
```json
{
  "name": "Lunch",
  "amount": 150,
  "category": "Food",
  "date": "2025-06-15"
}
```
