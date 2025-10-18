from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, os.environ.get("DATABASE_PATH", "db/db.db"))
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False  # True if you ever serve via HTTPS
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
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT user_id,type FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            conn.close()

            if result:
                session['logged_in'] = True
                session['username'] = username
                session['user_id'] = result[0]
                session['type'] = result[1]
               
                log_event('Login Success')
                return redirect(url_for('leaderboard'))
            else:
                
                return render_template('login.html', error="Login failed - user not found.")

        else:
            log_event(username, 'Login Failed', details="Invalid credentials")
            return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')

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

        log_event(username)
        return render_template('reset_password.html', message="Password reset successful. You may now log in.")

#        user = query_db("SELECT 1 FROM users WHERE username = ?", [username], one=True)
#        if user is None:
#            flash("Username not found. Please try again.", "error")
#            return redirect(url_for('reset_password'))

#        execute_db("UPDATE users SET password = ? WHERE username = ?", [hashed_password, username])
#        flash("Password reset successful! You can now log in.", "success")
#        return redirect(url_for('login'))

@app.template_filter('dateformat')
def dateformat(value, format='%d/%m/%y'):
    if not value:
        return ''
    if isinstance(value, str):
        value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return value.strftime(format)

@app.route('/leaderboard')
@login_required
def leaderboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    type = session.get('type') 

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # --- All-time leaderboard ---
    cursor.execute("""
    SELECT u.username as Name, SUM(a.points_earned) as total_points FROM users as u
    left join assignments as a
    on u.user_id = a.completed_by
    Where u.type = ?
    group by username
    Order by Total_points desc
""",(type,))
    all_time_data = cursor.fetchall()

    # --- Time-based leaderboard ---
    range = request.args.get('range', 'today')

    if range == '7days':
        cursor.execute("""
SELECT 
    u.username AS Name, 
    IFNULL(SUM(a.points_earned), 0) AS points
FROM users AS u
LEFT JOIN assignments AS a
    ON a.completed_by = u.user_id
    and date(a.date_completed) >= date('now', '-7 day')
    WHERE u.type = ?
GROUP BY u.username
ORDER BY points DESC;                 
    """,(type,))

    elif range == 'month':
        cursor.execute("""
        SELECT 
            u.username AS Name, 
            IFNULL(SUM(a.points_earned), 0) AS points
        FROM users AS u
        LEFT JOIN assignments AS a
            ON a.completed_by = u.user_id
        AND strftime('%Y-%m', a.date_completed) = strftime('%Y-%m', 'now', 'localtime')
        where u.type = ?                          
        GROUP BY u.username
        Order by points desc               
    """,(type,))

    else:  # today
        cursor.execute("""
        SELECT 
            u.username AS Name, 
            IFNULL(SUM(a.points_earned), 0) AS points
        FROM users AS u
        LEFT JOIN assignments AS a
            ON a.completed_by = u.user_id         
        AND date(a.date_completed) = date('now', 'localtime') 
        where u.type = ?
        GROUP BY u.username
        Order by points desc               
    """,(type,))

    time_filtered_data = cursor.fetchall()
    conn.close()

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

    from datetime import date, timedelta
    today = date.today()
    if not start_date:
        start_date = (today - timedelta(days=7)).isoformat()
    if not end_date:
        end_date = today.isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    users = conn.execute(
        "SELECT username, user_id FROM users WHERE type = ?",
        (user_type,)
    ).fetchall()

    chores = conn.execute(
        "SELECT chore_name, chore_id FROM chores WHERE type = ? ORDER BY chore_name ASC",
        (user_type,)
    ).fetchall()

    query = """
        SELECT
            u.username AS Name,
            c.chore_name AS Chore,
            a.date_completed AS [Completed on],
            a.points_earned AS Points
        FROM assignments a
        JOIN users  u ON u.user_id = a.completed_by    -- use assigned_to if that's your schema
        JOIN chores c ON c.chore_id = a.chore_id
        WHERE UPPER(a.status) IN ('APPROVED','COMPLETE')
        And u.type = ? 
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

    query += " ORDER BY a.date_completed DESC"

    chores_data = conn.execute(query, params).fetchall()
    conn.close()

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
    type = session.get('type')

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
    """, (user_id, type,))
    
    current_user_chores = cursor.fetchall()
    
    cursor.execute("""
        SELECT
          u.username AS 'Name',
          c.chore_name AS 'Chore',
          a.date_assigned AS 'Set when',
          a.assignment_id,
          a.status as status
        FROM assignments AS a
        INNER JOIN users AS u ON a.assigned_to = u.user_id
        INNER JOIN chores AS c ON a.chore_id = c.chore_id
        WHERE a.status != 'Complete'
        and a.status != 'Deleted'
          AND NOT u.user_id = ?
          AND u.type = ?
        ORDER BY a.date_assigned DESC
    """, (user_id, type,))
    other_user_chores = cursor.fetchall()

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

    if not session.get('logged_in'):
        return redirect(url_for('login'))
    type = session.get('type')

    if request.method == 'POST':
        assigned_to = int(request.form.get('assigned_to'))
        chore_id = request.form.get('chore_id')

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
          
        cursor.execute("""
            INSERT INTO assignments (
                chore_id,
                assigned_to,
                date_assigned,
                status,
                points_earned
            )
            VALUES (?, ?, current_timestamp, 'Pending',(SELECT points from chores
            where chore_id = ? ))
        """, (chore_id, assigned_to, chore_id,))
        conn.commit()
        conn.close()

        
        return redirect(url_for('assignments', selected_user=assigned_to, selected_chore=chore_id, selected_status=statusgive))
    
    selected_user = request.args.get('selected_user', type=int)
    selected_chore = request.args.get('selected_chore', type=int)
    selected_status = request.args.get('selected_status')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""SELECT username, user_id FROM users Where type = ?
    """,(type,))
    users = cursor.fetchall()

    cursor.execute("""SELECT chore_name, chore_id FROM chores Where type = ?
    """,(type,))
    chores = cursor.fetchall()

    conn.close()
    
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
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    type = session.get('type')
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'approve_all':
    
            cursor.execute("""
        SELECT c.assignment_id, c.assigned_to
        FROM assignments as c
        Inner join users as u
        on c.assigned_to = u.user_id
        WHERE c.status = 'Submitted' AND u.type = ?
    """,(type,))
            assignments = cursor.fetchall()

            for assignment_id, assigned_to in assignments:
                cursor.execute("""
            UPDATE assignments
            SET status = 'Complete',
                date_completed = current_timestamp,
                completed_by = ?
            WHERE assignment_id = ?
        """, (assigned_to, assignment_id,))

        else:
            assignment_id = request.form.get('assignment_id')

            if action == 'approve':
                result = query_db(
                    "SELECT assigned_to FROM assignments WHERE assignment_id = ?",
                    (assignment_id,),
                    one=True
                )
                if result:
                    assigned_to = result[0]
                    cursor.execute("""
                    UPDATE assignments
                    SET status = 'Complete',
                        date_completed = current_timestamp,
                        completed_by = ?
                    WHERE assignment_id = ?
                """, (assigned_to, assignment_id,))

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

   
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
          u.username AS 'Name',
          c.chore_name AS 'Chore',
          a.date_assigned AS 'Set when',
          a.assignment_id,
          a.status as status
        FROM assignments AS a
        INNER JOIN Users AS u ON a.assigned_to = u.user_id
        INNER JOIN Chores AS c ON a.chore_id = c.chore_id
        WHERE a.status = 'Submitted' and u.type = ?
        ORDER BY a.date_assigned DESC
    """,(type,))
    
    Submitted_chores = cursor.fetchall()
    
    conn.close()


    return render_template(
        'chore_completions.html',
        Submitted_chores=submitted_chores
    )

@app.route('/logout')
def logout():
    log_event(session.get('username'))
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host='0.0.0.0', port=5000, debug=True)