import os
import sqlite3
from datetime import date
from flask import Flask, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "blood.db")
TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

app = Flask(__name__, static_folder=os.path.join(BASE, "static"))


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init():
    # Create the database from the SQL file the first time only
    if not os.path.exists(DB):
        conn = sqlite3.connect(DB)
        with open(os.path.join(BASE, "blood_donation.sql"), encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()


init()


def rows(conn, sql):
    return [dict(r) for r in conn.execute(sql)]


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/state")
def state():
    conn = db()
    donors = rows(conn, "SELECT donor_id AS id, name, blood_type AS bt, city, phone, last_donation AS last FROM Donors")
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
    return jsonify(donors=donors, requests=requests_, stock=stock, donations=donations)


@app.post("/api/donors")
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
def add_request():
    j = request.get_json(force=True)
    if j.get("bt") not in TYPES or j.get("urg") not in ("Low", "Medium", "High") or not j.get("patient") or not j.get("city"):
        return jsonify(error="Please fill in all fields"), 400
    try:
        need = int(j.get("need", 0))
    except (TypeError, ValueError):
        need = 0
    if need < 1:
        return jsonify(error="Units needed must be at least 1"), 400
    conn = db()
    conn.execute("INSERT INTO Requests (patient_name, blood_type, units_needed, urgency, city) VALUES (?,?,?,?,?)",
                 (j["patient"].strip(), j["bt"], need, j["urg"], j["city"].strip()))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@app.post("/api/donate")
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
