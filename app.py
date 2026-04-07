from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, date

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = "expense_tracker_secret_key_2026_avadi"
CORS(app, supports_credentials=True, origins=["http://localhost:5000", "http://127.0.0.1:5000"])

DB_PATH = "expenses.db"

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# ── DB ──────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    salt = "xt_salt_2026"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

def init_db():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            monthly_limit REAL NOT NULL,
            UNIQUE(user_id, category),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )""")
        conn.commit()
    print("✅ Database ready!")

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({"error": "Please login first", "code": "AUTH_REQUIRED"}), 401
        return f(*args, **kwargs)
    return decorated

# ── AUTH ────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username","").strip().lower()
    password = data.get("password","").strip()
    name     = data.get("name","").strip()
    if not username or not password or not name:
        return jsonify({"error": "All fields are required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400
    try:
        with get_db() as conn:
            cur = conn.execute("INSERT INTO users (username,password,name) VALUES (?,?,?)",
                (username, hash_password(password), name))
            conn.commit()
            user_id = cur.lastrowid
        session['user_id']  = user_id
        session['username'] = username
        session['name']     = name
        return jsonify({"message": "Account created!", "name": name, "username": username}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already taken!"}), 409

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username","").strip().lower()
    password = data.get("password","").strip()
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=? AND password=?",
        (username, hash_password(password))).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "Wrong username or password!"}), 401
    session['user_id']  = user['id']
    session['username'] = user['username']
    session['name']     = user['name']
    return jsonify({"message": "Login successful!", "name": user['name'], "username": user['username']})

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})

@app.route("/api/auth/me", methods=["GET"])
def me():
    if not session.get('user_id'):
        return jsonify({"logged_in": False}), 401
    return jsonify({"logged_in": True, "user_id": session['user_id'],
        "username": session['username'], "name": session['name']})

# ── EXPENSES ────────────────────────────
@app.route("/api/expenses", methods=["GET"])
@login_required
def get_expenses():
    uid   = session['user_id']
    conn  = get_db()
    month = request.args.get("month")
    cat   = request.args.get("category")
    lim   = int(request.args.get("limit", 100))
    off   = int(request.args.get("offset", 0))
    q, p  = "SELECT * FROM expenses WHERE user_id=?", [uid]
    if month: q += " AND date LIKE ?"; p.append(f"{month}%")
    if cat:   q += " AND category=?";  p.append(cat)
    q += " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
    p += [lim, off]
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/expenses", methods=["POST"])
@login_required
def add_expense():
    uid  = session['user_id']
    data = request.get_json()
    name = data.get("name","").strip()
    amt  = data.get("amount")
    cat  = data.get("category","Other")
    dt   = data.get("date", str(date.today()))
    if not name or not amt or float(amt) <= 0:
        return jsonify({"error": "Invalid data"}), 400
    with get_db() as conn:
        cur = conn.execute("INSERT INTO expenses (user_id,name,amount,category,date) VALUES (?,?,?,?,?)",
            (uid, name, float(amt), cat, dt))
        conn.commit()
    return jsonify({"id": cur.lastrowid, "message": "Added!"}), 201

@app.route("/api/expenses/<int:exp_id>", methods=["DELETE"])
@login_required
def delete_expense(exp_id):
    uid = session['user_id']
    with get_db() as conn:
        d = conn.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (exp_id, uid)).rowcount
        conn.commit()
    return jsonify({"message": "Deleted"}) if d else (jsonify({"error": "Not found"}), 404)

# ── SUMMARY ─────────────────────────────
@app.route("/api/summary", methods=["GET"])
@login_required
def get_summary():
    uid = session['user_id']
    conn = get_db()
    mo  = str(date.today())[:7]
    total      = conn.execute("SELECT COALESCE(SUM(amount),0) as t FROM expenses WHERE user_id=?", (uid,)).fetchone()["t"]
    month_total= conn.execute("SELECT COALESCE(SUM(amount),0) as t FROM expenses WHERE user_id=? AND date LIKE ?", (uid,f"{mo}%")).fetchone()["t"]
    by_cat     = conn.execute("SELECT category, SUM(amount) as total FROM expenses WHERE user_id=? GROUP BY category ORDER BY total DESC", (uid,)).fetchall()
    monthly    = conn.execute("SELECT strftime('%Y-%m',date) as month, SUM(amount) as total FROM expenses WHERE user_id=? GROUP BY month ORDER BY month DESC LIMIT 6", (uid,)).fetchall()
    count      = conn.execute("SELECT COUNT(*) as c FROM expenses WHERE user_id=?", (uid,)).fetchone()["c"]
    days_row   = conn.execute("SELECT julianday('now')-julianday(MIN(date))+1 as d FROM expenses WHERE user_id=?", (uid,)).fetchone()
    days       = max(1, days_row["d"] or 1)
    conn.close()
    return jsonify({"total": round(total,2), "this_month": round(month_total,2),
        "avg_per_day": round(total/days,2), "transaction_count": count,
        "by_category": [{"category":r["category"],"total":round(r["total"],2)} for r in by_cat],
        "monthly": [{"month":r["month"],"total":round(r["total"],2)} for r in monthly]})

# ── BUDGETS ─────────────────────────────
@app.route("/api/budgets", methods=["GET"])
@login_required
def get_budgets():
    uid  = session['user_id']
    conn = get_db()
    mo   = str(date.today())[:7]
    buds = conn.execute("SELECT * FROM budgets WHERE user_id=?", (uid,)).fetchall()
    res  = []
    for b in buds:
        spent = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM expenses WHERE user_id=? AND category=? AND date LIKE ?",
            (uid, b["category"], f"{mo}%")).fetchone()["s"]
        pct = round((spent/b["monthly_limit"])*100,1) if b["monthly_limit"]>0 else 0
        res.append({"id":b["id"],"category":b["category"],"monthly_limit":b["monthly_limit"],
            "spent":round(spent,2),"remaining":round(b["monthly_limit"]-spent,2),
            "percent_used":pct,"status":"over" if pct>100 else "warning" if pct>80 else "ok"})
    conn.close()
    return jsonify(res)

@app.route("/api/budgets", methods=["POST"])
@login_required
def set_budget():
    uid  = session['user_id']
    data = request.get_json()
    cat  = data.get("category","").strip()
    lim  = data.get("monthly_limit")
    if not cat or not lim or float(lim)<=0:
        return jsonify({"error": "Invalid"}), 400
    with get_db() as conn:
        conn.execute("INSERT INTO budgets (user_id,category,monthly_limit) VALUES (?,?,?) ON CONFLICT(user_id,category) DO UPDATE SET monthly_limit=excluded.monthly_limit",
            (uid, cat, float(lim)))
        conn.commit()
    return jsonify({"message": f"Budget set for {cat}"}), 201

@app.route("/api/budgets/<int:bid>", methods=["DELETE"])
@login_required
def delete_budget(bid):
    uid = session['user_id']
    with get_db() as conn:
        conn.execute("DELETE FROM budgets WHERE id=? AND user_id=?", (bid, uid))
        conn.commit()
    return jsonify({"message": "Deleted"})

# ── HEALTH ──────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# ── MAIN ────────────────────────────────
if __name__ == "__main__":
    init_db()
    print("🚀 http://localhost:5000")
    app.run(debug=True, port=5000)
