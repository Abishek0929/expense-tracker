from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime, date
import calendar

app = Flask(__name__)
CORS(app)  # Allow frontend to connect

DB_PATH = "expenses.db"

# ─────────────────────────────────────────
# DB SETUP
# ─────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT    NOT NULL,
                amount    REAL    NOT NULL,
                category  TEXT    NOT NULL,
                date      TEXT    NOT NULL,
                created_at TEXT   DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                category  TEXT    NOT NULL UNIQUE,
                monthly_limit REAL NOT NULL
            )
        """)
        conn.commit()
    print("✅ Database initialized: expenses.db")

# ─────────────────────────────────────────
# EXPENSES API
# ─────────────────────────────────────────

@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    """Get all expenses with optional filters."""
    conn = get_db()
    
    month  = request.args.get("month")   # e.g. 2025-06
    cat    = request.args.get("category")
    limit  = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    query  = "SELECT * FROM expenses WHERE 1=1"
    params = []

    if month:
        query += " AND date LIKE ?"
        params.append(f"{month}%")
    if cat:
        query += " AND category = ?"
        params.append(cat)

    query += " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify([dict(r) for r in rows])


@app.route("/api/expenses", methods=["POST"])
def add_expense():
    """Add a new expense."""
    data = request.get_json()

    name     = data.get("name", "").strip()
    amount   = data.get("amount")
    category = data.get("category", "Other")
    exp_date = data.get("date", str(date.today()))

    if not name or not amount or float(amount) <= 0:
        return jsonify({"error": "Invalid name or amount"}), 400

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (name, amount, category, date) VALUES (?, ?, ?, ?)",
            (name, float(amount), category, exp_date)
        )
        conn.commit()
        new_id = cur.lastrowid

    return jsonify({"id": new_id, "message": "Expense added successfully"}), 201


@app.route("/api/expenses/<int:exp_id>", methods=["DELETE"])
def delete_expense(exp_id):
    """Delete an expense by ID."""
    with get_db() as conn:
        deleted = conn.execute("DELETE FROM expenses WHERE id = ?", (exp_id,)).rowcount
        conn.commit()

    if deleted == 0:
        return jsonify({"error": "Expense not found"}), 404
    return jsonify({"message": "Deleted successfully"})


@app.route("/api/expenses/<int:exp_id>", methods=["PUT"])
def update_expense(exp_id):
    """Update an expense."""
    data = request.get_json()
    fields, params = [], []

    for field in ["name", "amount", "category", "date"]:
        if field in data:
            fields.append(f"{field} = ?")
            params.append(data[field])

    if not fields:
        return jsonify({"error": "Nothing to update"}), 400

    params.append(exp_id)
    with get_db() as conn:
        conn.execute(f"UPDATE expenses SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()

    return jsonify({"message": "Updated successfully"})


# ─────────────────────────────────────────
# SUMMARY / ANALYTICS API
# ─────────────────────────────────────────

@app.route("/api/summary", methods=["GET"])
def get_summary():
    """Get spending summary: totals, by category, by month."""
    conn = get_db()

    total = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM expenses").fetchone()["total"]

    # Current month total
    this_month = str(date.today())[:7]
    month_total = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as t FROM expenses WHERE date LIKE ?",
        (f"{this_month}%",)
    ).fetchone()["t"]

    # Category breakdown
    by_cat = conn.execute(
        "SELECT category, SUM(amount) as total FROM expenses GROUP BY category ORDER BY total DESC"
    ).fetchall()

    # Monthly totals (last 6 months)
    monthly = conn.execute("""
        SELECT strftime('%Y-%m', date) as month, SUM(amount) as total
        FROM expenses
        GROUP BY month
        ORDER BY month DESC
        LIMIT 6
    """).fetchall()

    # Transaction count
    count = conn.execute("SELECT COUNT(*) as c FROM expenses").fetchone()["c"]

    # Average per day
    days_row = conn.execute("""
        SELECT julianday('now') - julianday(MIN(date)) + 1 as days FROM expenses
    """).fetchone()
    days = max(1, days_row["days"] or 1)

    conn.close()
    return jsonify({
        "total": round(total, 2),
        "this_month": round(month_total, 2),
        "avg_per_day": round(total / days, 2),
        "transaction_count": count,
        "by_category": [{"category": r["category"], "total": round(r["total"], 2)} for r in by_cat],
        "monthly": [{"month": r["month"], "total": round(r["total"], 2)} for r in monthly]
    })


# ─────────────────────────────────────────
# BUDGET API
# ─────────────────────────────────────────

@app.route("/api/budgets", methods=["GET"])
def get_budgets():
    """Get all budgets with current month spending."""
    conn   = get_db()
    month  = str(date.today())[:7]
    budgets = conn.execute("SELECT * FROM budgets").fetchall()
    result  = []

    for b in budgets:
        spent = conn.execute(
            "SELECT COALESCE(SUM(amount),0) as s FROM expenses WHERE category=? AND date LIKE ?",
            (b["category"], f"{month}%")
        ).fetchone()["s"]
        pct = round((spent / b["monthly_limit"]) * 100, 1) if b["monthly_limit"] > 0 else 0
        result.append({
            "id": b["id"],
            "category": b["category"],
            "monthly_limit": b["monthly_limit"],
            "spent": round(spent, 2),
            "remaining": round(b["monthly_limit"] - spent, 2),
            "percent_used": pct,
            "status": "over" if pct > 100 else "warning" if pct > 80 else "ok"
        })

    conn.close()
    return jsonify(result)


@app.route("/api/budgets", methods=["POST"])
def set_budget():
    """Set or update a budget for a category."""
    data     = request.get_json()
    category = data.get("category", "").strip()
    limit    = data.get("monthly_limit")

    if not category or not limit or float(limit) <= 0:
        return jsonify({"error": "Invalid category or limit"}), 400

    with get_db() as conn:
        conn.execute("""
            INSERT INTO budgets (category, monthly_limit)
            VALUES (?, ?)
            ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit
        """, (category, float(limit)))
        conn.commit()

    return jsonify({"message": f"Budget set for {category}"}), 201


@app.route("/api/budgets/<int:budget_id>", methods=["DELETE"])
def delete_budget(budget_id):
    with get_db() as conn:
        conn.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
        conn.commit()
    return jsonify({"message": "Budget deleted"})


# ─────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Expense Tracker API running 🚀"})


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("🚀 Starting Expense Tracker API on http://localhost:5000")
    app.run(debug=True, port=5000)
