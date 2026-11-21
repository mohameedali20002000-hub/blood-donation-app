-- Blood Donation System (SQLite - works directly with Python's sqlite3)

PRAGMA foreign_keys = ON;

-- ========== TABLES ==========
CREATE TABLE Donors (
    donor_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    blood_type      TEXT NOT NULL CHECK (blood_type IN ('A+','A-','B+','B-','AB+','AB-','O+','O-')),
    city            TEXT NOT NULL,
    phone           TEXT UNIQUE NOT NULL,
    last_donation   DATE
);

CREATE TABLE Requests (
    request_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name    TEXT NOT NULL,
    blood_type      TEXT NOT NULL CHECK (blood_type IN ('A+','A-','B+','B-','AB+','AB-','O+','O-')),
    units_needed    INTEGER NOT NULL CHECK (units_needed > 0),
    urgency         TEXT NOT NULL CHECK (urgency IN ('Low','Medium','High')),
    city            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ('Open','Fulfilled')),
    request_date    DATE NOT NULL DEFAULT (DATE('now'))
);

CREATE TABLE Donations (
    donation_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id        INTEGER NOT NULL,
    request_id      INTEGER,
    donation_date   DATE NOT NULL DEFAULT (DATE('now')),
    units           INTEGER NOT NULL DEFAULT 1 CHECK (units > 0),
    FOREIGN KEY (donor_id)   REFERENCES Donors(donor_id),
    FOREIGN KEY (request_id) REFERENCES Requests(request_id)
);

CREATE TABLE BloodStock (
    stock_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    blood_type      TEXT NOT NULL CHECK (blood_type IN ('A+','A-','B+','B-','AB+','AB-','O+','O-')),
    units           INTEGER NOT NULL CHECK (units >= 0),
    expiry_date     DATE NOT NULL
);

-- ========== SAMPLE DATA ==========
INSERT INTO Donors (name, blood_type, city, phone, last_donation) VALUES
('Ahmed Ali',     'O+',  'Cairo',      '01011111111', '2026-06-01'),
('Sara Hassan',   'A+',  'Giza',       '01022222222', '2026-10-20'),
('Omar Khaled',   'O+',  'Cairo',      '01033333333', NULL),
('Mona Samir',    'B-',  'Alexandria', '01044444444', '2026-05-10'),
('Youssef Adel',  'AB+', 'Cairo',      '01055555555', '2026-08-15');

INSERT INTO Requests (patient_name, blood_type, units_needed, urgency, city, status, request_date) VALUES
('Hany Mostafa',  'O+', 3, 'High',   'Cairo',      'Open',      '2026-11-18'),
('Laila Nabil',   'A+', 2, 'Medium', 'Giza',       'Open',      '2026-11-15'),
('Karim Fathy',   'B-', 1, 'High',   'Alexandria', 'Fulfilled', '2026-11-01');

INSERT INTO Donations (donor_id, request_id, donation_date, units) VALUES
(4, 3, '2026-11-02', 1),
(1, 1, '2026-11-19', 1),
(2, 2, '2026-11-20', 1);

INSERT INTO BloodStock (blood_type, units, expiry_date) VALUES
('O+', 12, '2026-12-30'),
('A+',  5, '2026-12-10'),
('B-',  2, '2026-11-28'),
('AB+', 1, '2027-01-05');

-- ========== SEARCH WITH FILTER ==========
-- Search donors by blood type + city
SELECT donor_id, name, blood_type, city, phone
FROM Donors
WHERE blood_type = 'O+' AND city = 'Cairo';

-- Search donors by name (partial) + blood type
SELECT * FROM Donors
WHERE name LIKE '%Ahmed%' AND blood_type = 'O+';

-- ========== SMART MATCHING (the creative part) ==========
-- Eligible donors for request #1: same blood type, same city,
-- never donated or last donation more than 90 days ago
SELECT d.donor_id, d.name, d.phone, d.last_donation
FROM Donors d
JOIN Requests r ON r.blood_type = d.blood_type AND r.city = d.city
WHERE r.request_id = 1
  AND (d.last_donation IS NULL OR julianday('now') - julianday(d.last_donation) >= 90);

-- ========== REPORTS ==========
-- 1) Stock per blood type
SELECT blood_type, SUM(units) AS total_units
FROM BloodStock
GROUP BY blood_type
ORDER BY total_units DESC;

-- 2) Urgent open requests
SELECT request_id, patient_name, blood_type, units_needed, city
FROM Requests
WHERE status = 'Open' AND urgency = 'High';

-- 3) Most active donors
SELECT d.name, COUNT(*) AS donations_count, SUM(dn.units) AS total_units
FROM Donations dn
JOIN Donors d ON d.donor_id = dn.donor_id
GROUP BY d.donor_id
ORDER BY donations_count DESC;

-- 4) Monthly donations
SELECT strftime('%Y-%m', donation_date) AS month, SUM(units) AS total_units
FROM Donations
GROUP BY month
ORDER BY month;

-- 5) Low stock alert (less than 3 units) or expiring within 14 days
SELECT blood_type, units, expiry_date
FROM BloodStock
WHERE units < 3
   OR julianday(expiry_date) - julianday('now') <= 14;
