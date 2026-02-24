# --- Standard library imports ---
import os
import sqlite3
from functools import wraps
from datetime import date, timedelta
from pathlib import Path
# --- Third-party imports ---
import bcrypt
from flask import (redirect, session, url_for)
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, os.environ.get("DATABASE_PATH", "db/db.db"))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
            
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def query_db(query, args=(), one=False):
    with get_db() as conn:
        cur = conn.execute(query, args)
        rv = cur.fetchall()
        cur.close()
        return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, args)
        conn.commit()
        cur.close()

def get_date_range(start_date, end_date):
    today = date.today()
    if not start_date:
        start_date = (today - timedelta(days=7)).isoformat()
    if not end_date:
        end_date = today.isoformat()
    return start_date, end_date

def check_login(username, password):
    user = query_db("SELECT password FROM users WHERE username = ?", (username,), one=True)
    if not user:
        return False
    stored_hash = user['password']
    return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
