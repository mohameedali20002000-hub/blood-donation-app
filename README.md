# Blood Donation Network

## Run locally
    pip install -r requirements.txt
    python app.py
Open http://localhost:5000

The database (blood.db) is created automatically from blood_donation.sql on first run.
To reset the data, delete blood.db and run again.

## Deploy (Render / PythonAnywhere)
- Start command: gunicorn app:app
- Note: on free plans the SQLite file may reset when the server restarts.
