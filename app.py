# --- Standard library imports ---
import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
# --- Third-party imports ---
import bcrypt
from dotenv import load_dotenv
from flask import (Flask, flash, get_flashed_messages,
    redirect, render_template, request,
    session, url_for)
load_dotenv()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, os.environ.get("DATABASE_PATH", "db/db.db"))
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False
)
        
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

@app.template_filter('dateformat')
def dateformat(value, format='%d/%m/%y'):
    if not value:
        return ''
    if isinstance(value, str):
        value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return value.strftime(format)

@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if check_login(username, password):
            user = query_db(
                "SELECT user_id, type FROM users WHERE username = ?",
                [username],
                one=True
            )

            if user:
                session.update({
                    'logged_in': True,
                    'username': username,
                    'user_id': user['user_id'],
                    'type': user['type']
                })
                flash("Login successful!", "success")
                return redirect(url_for('leaderboard'))

            flash("Login failed – user not found.", "error")
            return redirect(url_for('login'))

        flash("Invalid credentials. Please try again.", "error")
        return redirect(url_for('login'))
    print(get_flashed_messages(with_categories=True))

    return render_template('login.html')
#For if I ever want to enable password reset testing this is a change
#@app.route('/reset_password', methods=['GET', 'POST'])
#def reset_password():
#    if request.method == 'POST':
#        username = request.form['reset_username']
#        new_password = request.form['new_password']
#        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

#        user = query_db("SELECT 1 FROM users WHERE username = ?", [username], one=True)
#        if user is None:
#            flash("Username not found. Please try again.", "error")
#            return redirect(url_for('reset_password'))

#        execute_db("UPDATE users SET password = ? WHERE username = ?", [hashed_password, username])
#        flash("Password reset successful! You can now log in.", "success")
#        return redirect(url_for('login'))

#    return render_template('reset_password.html')

@app.route('/leaderboard')
@login_required
def leaderboard():
    user_type = session.get('type') 
    # --- All-time leaderboard ---
    all_time_data = query_db("""
        SELECT u.username as Name, SUM(a.points_earned) as total_points 
        FROM users as u
        LEFT JOIN assignments as a ON u.user_id = a.completed_by
        WHERE u.type = ?
        GROUP BY username
        ORDER BY total_points DESC
    """, (user_type,))
    # --- Time-based leaderboard ---
    time_range = request.args.get('range', 'today')
    if time_range == '7days':
        time_filtered_data = query_db("""
            SELECT u.username AS Name, IFNULL(SUM(a.points_earned), 0) AS points
            FROM users AS u
            LEFT JOIN assignments AS a
                ON a.completed_by = u.user_id
                AND date(a.date_completed) >= date('now', '-7 day')
            WHERE u.type = ?
            GROUP BY u.username
            ORDER BY points DESC
        """, (user_type,))
    elif time_range == 'month':
        time_filtered_data = query_db("""
            SELECT u.username AS Name, IFNULL(SUM(a.points_earned), 0) AS points
            FROM users AS u
            LEFT JOIN assignments AS a
                ON a.completed_by = u.user_id
                AND strftime('%Y-%m', a.date_completed) = strftime('%Y-%m', 'now', 'localtime')
            WHERE u.type = ?
            GROUP BY u.username
            ORDER BY points DESC
        """, (user_type,))
    else:  # today
        time_filtered_data = query_db("""
            SELECT u.username AS Name, IFNULL(SUM(a.points_earned), 0) AS points
            FROM users AS u
            LEFT JOIN assignments AS a
                ON a.completed_by = u.user_id         
                AND date(a.date_completed) = date('now', 'localtime') 
            WHERE u.type = ?
            GROUP BY u.username
            ORDER BY points DESC
        """, (user_type,))

    return render_template(
        "leaderboard.html",
        all_time_data=all_time_data,
        time_filtered_data=time_filtered_data,
        selected_range=time_range
    )

@app.route('/chore_history')
@login_required
def chore_history():

    user_type = session.get('type') 
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    selected_user = request.args.get('user', type=int)
    selected_chore = request.args.get('chore', type=int)
    start_date, end_date = get_date_range(start_date, end_date)
    users = query_db(
        "SELECT username, user_id FROM users WHERE type = ?",
        (user_type,)
    )
    chores = query_db(
        "SELECT chore_name, chore_id FROM chores WHERE type = ? ORDER BY chore_name ASC",
        (user_type,)
    )
    base_query = """
    SELECT u.username AS Name,
           c.chore_name AS Chore,
           a.date_completed AS completed_on,
           a.points_earned AS Points
    FROM assignments a
    JOIN users u ON u.user_id = a.completed_by
    JOIN chores c ON c.chore_id = a.chore_id
    WHERE UPPER(a.status) IN ('APPROVED','COMPLETE')
      AND u.type = ? 
      AND datetime(a.date_completed) >= datetime(?, 'start of day')
      AND datetime(a.date_completed) <  datetime(?, '+1 day', 'start of day')
"""
    params = [user_type, start_date, end_date]

    if selected_user:
        base_query += " AND u.user_id = ?"
        params.append(selected_user)

    if selected_chore:
        base_query += " AND c.chore_id = ?"
        params.append(selected_chore)

    base_query += " ORDER BY a.date_completed DESC"

    chores_data = query_db(base_query, params)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render_template('partials/chore_history_table.html', chores_data=chores_data)

    return render_template(
        'chore_history.html',
        chores_data=chores_data,
        users=users,
        chores=chores,
        start_date=start_date,
        end_date=end_date,
        selected_user=selected_user,
        selected_chore=selected_chore
    )

@app.route('/active_chores', methods=['GET', 'POST'])
@login_required
def active_chores():

    user_id = session.get('user_id')
    user_type = session.get('type')

    if request.method == 'POST':
        assignment_id = request.form.get('assignment_id')
        execute_db("""
            UPDATE assignments
            SET status = 'Submitted',
                assigned_to = ?           
            WHERE assignment_id = ?
        """, (user_id, assignment_id))
        return redirect(url_for('active_chores'))

    current_user_chores = query_db("""
        SELECT u.username AS name,
               c.chore_name AS chore,
               a.date_assigned AS set_when,
               a.assignment_id,
               a.status
        FROM assignments a
        JOIN users u ON a.assigned_to = u.user_id
        JOIN chores c ON a.chore_id = c.chore_id
        WHERE a.status NOT IN ('Complete','Deleted')
          AND u.user_id = ?
          AND u.type = ?
        ORDER BY a.date_assigned DESC
    """, (user_id, user_type))

    other_user_chores = query_db("""
        SELECT u.username AS name,
               c.chore_name AS chore,
               a.date_assigned AS set_when,
               a.assignment_id,
               a.status
        FROM assignments a
        JOIN users u ON a.assigned_to = u.user_id
        JOIN chores c ON a.chore_id = c.chore_id
        WHERE a.status NOT IN ('Complete','Deleted')
          AND u.user_id != ?
          AND u.type = ?
        ORDER BY a.date_assigned DESC
    """, (user_id, user_type))

    my_active_chores = query_db("""
        SELECT COUNT(assignment_id) AS count
        FROM assignments 
        WHERE assigned_to = ? 
          AND status IN ('Pending', 'Sent Back')
    """, (user_id,), one=True)
    my_active_chores = my_active_chores['count'] if my_active_chores else 0

    return render_template(
        'active_chores.html',
        current_user_chores=current_user_chores,
        other_user_chores=other_user_chores,
        active_chores=my_active_chores
    )

@app.route('/assignments', methods=['GET', 'POST'])
@login_required
def assignments():
    user_type = session.get('type')

    if request.method == 'POST':
        assigned_to = int(request.form.get('assigned_to'))
        chore_id = request.form.get('chore_id')
        statusgive = request.form.get('statusgive')
          
        execute_db("""
            INSERT INTO assignments (
                chore_id,
                assigned_to,
                date_assigned,
                status,
                points_earned
            )
            VALUES (?, ?, current_timestamp, ?,(SELECT points from chores
            where chore_id = ? ))
        """, (chore_id, assigned_to, statusgive, chore_id))
        
        return redirect(url_for('assignments', selected_user=assigned_to, selected_chore=chore_id, selected_status=statusgive))
    
    selected_user = request.args.get('selected_user', type=int)
    selected_chore = request.args.get('selected_chore', type=int)
    selected_status = request.args.get('selected_status')

    users = query_db("""SELECT username, user_id FROM users Where type = ?
    """,(user_type,))

    chores = query_db("""SELECT chore_name, chore_id FROM chores Where type = ? Order by chore_name asc
    """,(user_type,))

    status = query_db("""SELECT status FROM statuslist
    """)


    return render_template(
        'assignments.html',
        users=users,
        chores=chores,
        status=status,
        selected_user=selected_user,
        selected_chore=selected_chore,
        selected_status=selected_status
    )

@app.route('/chore_completions', methods=['GET', 'POST'])
@login_required
def chore_completions():
    user_type = session.get('type')

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'approve_all':
            assignments = query_db("""
                SELECT c.assignment_id, c.assigned_to
                FROM assignments c
                JOIN users u ON c.assigned_to = u.user_id
                WHERE c.status = 'Submitted' AND u.type = ?
                Order by c.chore_id desc                   
            """, (user_type,))

            for assignment in assignments:
                execute_db("""
                    UPDATE assignments
                    SET status = 'Complete',
                        date_completed = current_timestamp,
                        completed_by = ?
                    WHERE assignment_id = ?
                """, (assignment['assigned_to'], assignment['assignment_id']))

        else:
            assignment_id = request.form.get('assignment_id')

            if action == 'approve':
                result = query_db(
                    "SELECT assigned_to FROM assignments WHERE assignment_id = ?",
                    (assignment_id,),
                    one=True
                )
                if result:
                    execute_db("""
                        UPDATE assignments
                        SET status = 'Complete',
                            date_completed = current_timestamp,
                            completed_by = ?
                        WHERE assignment_id = ?
                    """, (result['assigned_to'], assignment_id))

            elif action == 'send_back':
                execute_db(
                    "UPDATE assignments SET status = 'Sent Back' WHERE assignment_id = ?",
                    (assignment_id,)
                )

            elif action == 'delete':
                execute_db(
                    "UPDATE assignments SET status = 'Deleted' WHERE assignment_id = ?",
                    (assignment_id,)
                )

        return redirect(url_for('chore_completions'))

    submitted_chores = query_db("""
        SELECT u.username AS name,
               c.chore_name AS chore,
               a.date_assigned AS set_when,
               a.assignment_id,
               a.status
        FROM assignments a
        JOIN users u ON a.assigned_to = u.user_id
        JOIN chores c ON a.chore_id = c.chore_id
        WHERE a.status = 'Submitted' AND u.type = ?
        ORDER BY a.date_assigned DESC
    """, (user_type,))

    return render_template(
        'chore_completions.html',
        Submitted_chores=submitted_chores
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host='0.0.0.0', port=5000, debug=True)