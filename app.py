import os
import sqlite3
from datetime import date
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "blood.db")
TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

app = Flask(__name__, static_folder=os.path.join(BASE, "static"))
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)

# Random secret key, generated once on the server and kept out of the repository
KEY_FILE = os.path.join(BASE, "secret.key")
if not os.path.exists(KEY_FILE):
    with open(KEY_FILE, "wb") as f:
        f.write(os.urandom(32))
with open(KEY_FILE, "rb") as f:
    app.secret_key = f.read()


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init():
    if not os.path.exists(DB):
        conn = sqlite3.connect(DB)
        with open(os.path.join(BASE, "blood_donation.sql"), encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
    conn = db()
    conn.execute("""CREATE TABLE IF NOT EXISTS Users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin','donor')),
        donor_id INTEGER,
        FOREIGN KEY (donor_id) REFERENCES Donors(donor_id))""")
    if not conn.execute("SELECT 1 FROM Users WHERE username = 'admin'").fetchone():
        pw = os.environ.get("ADMIN_PASSWORD", "admin123")
        conn.execute("INSERT INTO Users (username, password_hash, role) VALUES ('admin', ?, 'admin')",
                     (generate_password_hash(pw),))
    conn.commit()
    conn.close()


init()


def need(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **k):
            u = session.get("user")
            if not u:
                return jsonify(error="Please sign in"), 401
            if role and u["role"] != role:
                return jsonify(error="Admins only"), 403
            return f(*a, **k)
        return wrapper
    return deco


def rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args)]


def login_session(user_id, username, role, donor_id):
    session["user"] = {"id": user_id, "username": username, "role": role, "donor_id": donor_id}


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/me")
def me():
    return jsonify(user=session.get("user"))


@app.post("/api/login")
def login():
    j = request.get_json(force=True)
    conn = db()
    u = conn.execute("SELECT * FROM Users WHERE username = ?", (str(j.get("username", "")).strip(),)).fetchone()
    conn.close()
    if not u or not check_password_hash(u["password_hash"], str(j.get("password", ""))):
        return jsonify(error="Wrong username or password"), 401
    login_session(u["user_id"], u["username"], u["role"], u["donor_id"])
    return jsonify(ok=True)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.post("/api/register")
def register():
    j = request.get_json(force=True)
    username = str(j.get("username", "")).strip()
    name, city, phone = (str(j.get(k, "")).strip() for k in ("name", "city", "phone"))
    if j.get("bt") not in TYPES or not (username and name and city and phone):
        return jsonify(error="Please fill in all fields"), 400
    if len(str(j.get("password", ""))) < 4:
        return jsonify(error="Password must be at least 4 characters"), 400
    conn = db()
    try:
        cur = conn.execute("INSERT INTO Donors (name, blood_type, city, phone) VALUES (?,?,?,?)",
                           (name, j["bt"], city, phone))
        donor_id = cur.lastrowid
        cur = conn.execute("INSERT INTO Users (username, password_hash, role, donor_id) VALUES (?,?, 'donor', ?)",
                           (username, generate_password_hash(str(j["password"])), donor_id))
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        msg = "Username already taken" if "username" in str(e).lower() else "This phone number is already registered"
        return jsonify(error=msg), 400
    finally:
        conn.close()
    login_session(cur.lastrowid, username, "donor", donor_id)
    return jsonify(ok=True)


@app.get("/api/state")
@need()
def state():
    u = session["user"]
    conn = db()
    base = "SELECT donor_id AS id, name, blood_type AS bt, city, phone, last_donation AS last FROM Donors"
    if u["role"] == "admin":
        donors = rows(conn, base)
    else:  # a donor only sees their own record
        donors = rows(conn, base + " WHERE donor_id = ?", (u["donor_id"],))
    donor_count = conn.execute("SELECT COUNT(*) FROM Donors").fetchone()[0]
    requests_ = rows(conn, """
        SELECT r.request_id AS id, patient_name AS patient, r.blood_type AS bt, units_needed AS need,
               COALESCE((SELECT SUM(units) FROM Donations d WHERE d.request_id = r.request_id), 0) AS got,
               urgency AS urg, city, status
        FROM Requests r""")
    stock = {t: {"u": 0, "e": "9999-12-31"} for t in TYPES}
    for r in conn.execute("SELECT blood_type, SUM(units) AS u, MIN(expiry_date) AS e FROM BloodStock GROUP BY blood_type"):
        stock[r["blood_type"]] = {"u": r["u"], "e": r["e"]}
    donations = rows(conn, "SELECT donor_id AS d, request_id AS r, donation_date AS date FROM Donations")
    conn.close()
    return jsonify(donors=donors, requests=requests_, stock=stock, donations=donations, donor_count=donor_count)


@app.post("/api/donors")
@need("admin")
def add_donor():
    j = request.get_json(force=True)
    if j.get("bt") not in TYPES or not j.get("name") or not j.get("city") or not j.get("phone"):
        return jsonify(error="Please fill in all fields"), 400
    conn = db()
    try:
        conn.execute("INSERT INTO Donors (name, blood_type, city, phone) VALUES (?,?,?,?)",
                     (j["name"].strip(), j["bt"], j["city"].strip(), j["phone"].strip()))
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="This phone number is already registered"), 400
    finally:
        conn.close()
    return jsonify(ok=True)


@app.post("/api/requests")
@need()
def add_request():
    j = request.get_json(force=True)
    if j.get("bt") not in TYPES or j.get("urg") not in ("Low", "Medium", "High") or not j.get("patient") or not j.get("city"):
        return jsonify(error="Please fill in all fields"), 400
    try:
        need_units = int(j.get("need", 0))
    except (TypeError, ValueError):
        need_units = 0
    if need_units < 1:
        return jsonify(error="Units needed must be at least 1"), 400
    conn = db()
    conn.execute("INSERT INTO Requests (patient_name, blood_type, units_needed, urgency, city) VALUES (?,?,?,?,?)",
                 (j["patient"].strip(), j["bt"], need_units, j["urg"], j["city"].strip()))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@app.post("/api/donate")
@need("admin")
def donate():
    j = request.get_json(force=True)
    conn = db()
    req = conn.execute("SELECT units_needed FROM Requests WHERE request_id = ? AND status = 'Open'", (j.get("request"),)).fetchone()
    donor = conn.execute("SELECT donor_id FROM Donors WHERE donor_id = ?", (j.get("donor"),)).fetchone()
    if not req or not donor:
        conn.close()
        return jsonify(error="Request or donor not found"), 404
    today = date.today().isoformat()
    conn.execute("INSERT INTO Donations (donor_id, request_id, donation_date, units) VALUES (?,?,?,1)",
                 (donor["donor_id"], j["request"], today))
    conn.execute("UPDATE Donors SET last_donation = ? WHERE donor_id = ?", (today, donor["donor_id"]))
    got = conn.execute("SELECT SUM(units) FROM Donations WHERE request_id = ?", (j["request"],)).fetchone()[0]
    if got >= req["units_needed"]:
        conn.execute("UPDATE Requests SET status = 'Fulfilled' WHERE request_id = ?", (j["request"],))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

