from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os, bcrypt,hashlib
from pathlib import Path
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'db', 'db.db')

template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

app.secret_key = '4be5b4b95f0c076bc1bb51bfdc45e48794046c281d2f95060c4b2d9cf3d757b9'

def check_login(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        return False  # No user found

    stored_hash = result[0]

    # Check if this is a bcrypt hash
    if stored_hash.startswith("$2b$"):
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    else:
        # Legacy SHA-256 check
        input_hash = hashlib.sha256(password.encode()).hexdigest()
        if input_hash == stored_hash:
            # Upgrade to bcrypt
            new_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE Users SET password_hash = ? WHERE user_name = ?", (new_hash, username))
            conn.commit()
            conn.close()
            return True
        else:
            return False
            
def log_event(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM Users WHERE username = ?", (username,))
    result = cursor.fetchone()

    conn.commit()
    conn.close()

@app.route('/')
def root_redirect():
    return redirect(url_for('login'))


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

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form['reset_username']
        new_password = request.form['new_password']
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        
        cursor.execute("SELECT 1 FROM Users WHERE username = ?", (username,))
        if cursor.fetchone() is None:
            conn.close()
            return render_template('reset_password.html', error="Username not found. Please try again.")

        
        cursor.execute("""
            UPDATE Users
            SET password = ?
            WHERE username = ?
        """, (hashed_password, username))
        conn.commit()
        conn.close()

        log_event(username)
        return render_template('reset_password.html', message="Password reset successful. You may now log in.")

    return render_template('reset_password.html')


@app.template_filter('dateformat')
def dateformat(value, format='%d/%m/%y'):
    if not value:
        return ''
    if isinstance(value, str):
        value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return value.strftime(format)

@app.route('/leaderboard')
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
        selected_range=range
    )

@app.route('/chore_history')
def chore_history():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

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
        query += " AND u.user_id = ?"
        params.append(selected_user)
    if selected_chore:
        query += " AND c.chore_id = ?"
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
def active_chores():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    type = session.get('type')

    if request.method == 'POST':
        assignment_id = request.form.get('assignment_id')
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE assignments
            SET status = 'Submitted',
            Assigned_to = ?           
            WHERE Assignment_ID = ?
        """, (user_id, assignment_id,))
        conn.commit()
        conn.close()
        return redirect(url_for('active_chores'))  

    
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
        INNER JOIN users AS u ON a.assigned_to = u.user_id
        INNER JOIN chores AS c ON a.chore_id = c.chore_id
        WHERE a.status != 'Complete'
          and a.status != 'Deleted'
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

    
    cursor.execute("""
        SELECT COUNT(assignment_id) FROM assignments 
        WHERE assigned_to = ? AND status in ('Pending', 'Sent Back')
    """, (user_id,))
    result = cursor.fetchone()
    my_active_chores = result[0] if result else 0
    

    conn.close()
    
    return render_template(
        'active_chores.html',
        current_user_chores=current_user_chores,
        other_user_chores=other_user_chores,
        active_chores=my_active_chores
    )

@app.route('/assignments', methods=['GET', 'POST'])
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

        
        return redirect(url_for('assignments', selected_user=assigned_to, selected_chore=chore_id))

    
    selected_user = request.args.get('selected_user', type=int)
    selected_chore = request.args.get('selected_chore', type=int)

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
        selected_user=selected_user,
        selected_chore=selected_chore
    )


@app.route('/chore_completions', methods=['GET', 'POST'])
def chore_completions():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    type = session.get('type')
    if request.method == 'POST':
        action = request.form.get('action')

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

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
            
                cursor.execute("SELECT assigned_to FROM assignments WHERE assignment_id = ?", (assignment_id,))
                result = cursor.fetchone()
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
                cursor.execute("""
                UPDATE assignments
                SET status = 'Sent Back'
                WHERE assignment_id = ?
            """, (assignment_id,))
                
            elif action == 'delete':
                cursor.execute("""
                UPDATE assignments
                SET status = 'Deleted'
                WHERE assignment_id = ?
            """, (assignment_id,))    

        conn.commit()
        conn.close()
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
        Submitted_chores=Submitted_chores
    )

@app.route('/logout')
def logout():
    log_event(session.get('username'))
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)


