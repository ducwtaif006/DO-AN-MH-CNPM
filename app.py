from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3, hashlib, os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'xyz_meeting_admin_secret'
DB = 'meeting.db'

# ─── DB helpers ───────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def q(sql, args=(), one=False):
    conn = get_db()
    cur = conn.execute(sql, args)
    rv = cur.fetchone() if one else cur.fetchall()
    conn.close()
    return rv

def ex(sql, args=()):
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ─── Login required decorator ────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ─── Init DB ─────────────────────────────────────────────────
def init_db():
    conn = get_db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'employee',
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        last_login TEXT
    );
    CREATE TABLE IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT
    );
    CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role_name TEXT NOT NULL,
        perm_group TEXT NOT NULL,
        perm_name TEXT NOT NULL,
        enabled INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT,
        type TEXT DEFAULT 'info',
        is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name TEXT,
        action_type TEXT,
        action TEXT,
        ip TEXT,
        result TEXT DEFAULT 'success',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    CREATE TABLE IF NOT EXISTS meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        room TEXT,
        start_time TEXT,
        end_time TEXT,
        organizer TEXT,
        department TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        capacity INTEGER DEFAULT 10,
        status TEXT DEFAULT 'active'
    );
    ''')
    conn.commit()

    # seed data if empty
    if not conn.execute('SELECT 1 FROM users').fetchone():
        users = [
            ('Bùi Đức Tài',           'tai@company.vn', hash_pw('admin123'), 'admin', 'active'),
            ('Trần Hương',            'thuong@company.vn', hash_pw('admin123'), 'admin', 'active'),
            ('Lê Minh',               'leminh@company.vn', hash_pw('123456'), 'manager', 'active'),
            ('Lê Huỳnh Yến Nhi',      'ynhi@company.vn',  hash_pw('123456'), 'manager', 'inactive'),
            ('Phạm Lan',              'plan@company.vn',   hash_pw('123456'), 'employee', 'active'),
            ('Phạm Thị Nhi',          'nhi@company.vn', hash_pw('123456'), 'manager', 'banned'),
            ('Bùi Nhi',               'bnhi@company.vn',   hash_pw('123456'), 'employee', 'active'),
            ('Phương Nga',            'nga@company.vn',   hash_pw('123456'), 'employee', 'active'),
        ]
        conn.executemany('INSERT INTO users (fullname,email,password,role,status) VALUES (?,?,?,?,?)', users)

        roles = [
            ('admin',    'Quản trị viên hệ thống, toàn quyền truy cập'),
            ('manager',  'Quản lý phòng họp, quản lý lịch'),
            ('employee', 'Nhân viên, sử dụng lịch họp'),
        ]
        conn.executemany('INSERT INTO roles (name,description) VALUES (?,?)', roles)

        perms = [
            # admin
            ('admin','Quản lý tài khoản','Xem danh sách tài khoản',1),
            ('admin','Quản lý tài khoản','Tạo tài khoản mới',1),
            ('admin','Quản lý tài khoản','Chỉnh sửa tài khoản',1),
            ('admin','Quản lý tài khoản','Khoá / Mở khoá tài khoản',1),
            ('admin','Quản lý tài khoản','Phân quyền vai trò',1),
            ('admin','Quản lý phòng họp','Xem danh sách phòng họp',1),
            ('admin','Quản lý phòng họp','Thêm / Sửa / Xoá phòng họp',1),
            ('admin','Quản lý lịch họp','Xem tất cả lịch họp',1),
            ('admin','Quản lý lịch họp','Tạo / Sửa / Huỷ lịch họp',1),
            ('admin','Dashboard & Thống kê','Xem Dashboard',1),
            ('admin','Dashboard & Thống kê','Xem thống kê hiệu suất',1),
            ('admin','Dashboard & Thống kê','Xuất báo cáo',1),
            # manager
            ('manager','Quản lý phòng họp','Xem danh sách phòng họp',1),
            ('manager','Quản lý phòng họp','Thêm / Sửa / Xoá phòng họp',1),
            ('manager','Quản lý lịch họp','Xem tất cả lịch họp',1),
            ('manager','Quản lý lịch họp','Tạo / Sửa / Huỷ lịch họp',1),
            ('manager','Dashboard & Thống kê','Xem Dashboard',1),
            ('manager','Dashboard & Thống kê','Xem thống kê hiệu suất',1),
            ('manager','Dashboard & Thống kê','Xuất báo cáo',0),
            # employee
            ('employee','Quản lý lịch họp','Xem lịch họp cá nhân',1),
            ('employee','Quản lý lịch họp','Tạo lịch họp mới',1),
            ('employee','Quản lý lịch họp','Sửa / Huỷ lịch họp của mình',1),
            ('employee','Dashboard & Thống kê','Xem Dashboard',0),
            ('employee','Dashboard & Thống kê','Xuất báo cáo',0),
        ]
        conn.executemany('INSERT INTO permissions (role_name,perm_group,perm_name,enabled) VALUES (?,?,?,?)', perms)

        notifs = [
            ('Tài khoản bị khoá','Phạm Thị Nhi đã bị khoá do đăng nhập sai 5 lần.','danger',0),
            ('Tài khoản mới đăng ký','Nguyễn Thị C đăng ký, chờ duyệt.','warning',0),
            ('Xung đột lịch họp','Phòng A bị đặt trùng 14:00–15:00.','warning',0),
            ('Phòng họp cần bảo trì','Phòng B báo lỗi máy chiếu.','danger',0),
            ('Cập nhật quyền thành công','Quyền vai trò Quản lý đã cập nhật.','success',0),
            ('Đăng nhập thiết bị mới','Trần Hương đăng nhập từ Chrome/Win.','info',1),
            ('Lịch họp Sprint Planning','Đã tạo thành công bởi Trần Hương.','info',1),
        ]
        conn.executemany('INSERT INTO notifications (title,body,type,is_read) VALUES (?,?,?,?)', notifs)

        logs = [
            ('Trần Hương','Quản trị','Khoá tài khoản Phạm Thị Nhi','192.168.1.10','success'),
            ('Phạm Thị Nhi','Bảo mật','Đăng nhập sai mật khẩu lần 5','10.0.0.42','failed'),
            ('Lê Minh','Lịch họp','Tạo lịch họp Sprint Planning Q3','192.168.1.22','success'),
            ('Bùi Đức Tài','Quản trị','Cập nhật quyền vai trò Quản lý','192.168.1.1','success'),
            ('Phạm Lan','Đăng nhập','Đăng nhập hệ thống','192.168.1.31','success'),
            ('Bùi Nhi','Lịch họp','Hủy cuộc họp Đánh giá Q2','192.168.1.44','cancelled'),
            ('Bùi Đức Tài','Quản trị','Thêm phòng họp G','192.168.1.1','success'),
        ]
        conn.executemany('INSERT INTO activity_logs (user_name,action_type,action,ip,result) VALUES (?,?,?,?,?)', logs)

        settings_data = [
            ('company_name','Công ty XYZ'),
            ('timezone','GMT+7'),
            ('language','Tiếng Việt'),
            ('date_format','DD/MM/YYYY'),
            ('work_start','08:00'),
            ('work_end','18:00'),
            ('meeting_duration','60'),
            ('max_book_days','30'),
            ('notify_reminder','1'),
            ('notify_email','1'),
            ('notify_app','1'),
            ('two_fa','0'),
            ('max_login_fail','5'),
            ('session_hours','8'),
            ('auto_backup','1'),
            ('backup_freq','daily'),
            ('log_days','90'),
            ('smtp_host','smtp.company.vn'),
            ('smtp_port','587'),
            ('smtp_ssl','1'),
        ]
        conn.executemany('INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)', settings_data)

        meetings_data = [
            ('Sprint Planning Q3','Phòng A','2026-06-01 09:00','2026-06-01 10:00','Trần Hương','Kỹ thuật','active'),
            ('Họp dự án Website','Phòng B','2026-06-01 10:30','2026-06-01 11:30','Lê Minh','Kỹ thuật','active'),
            ('Đánh giá nhân sự Q2','Phòng C','2026-06-02 14:00','2026-06-02 15:00','Bùi Nhi','Nhân sự','cancelled'),
            ('Review sản phẩm v2.0','Phòng A','2026-06-03 15:00','2026-06-03 16:00','Phạm Lan','Nhân sự','active'),
            ('Họp ngân sách tháng 7','Phòng D','2026-06-04 16:30','2026-06-04 17:30','Lê Minh','Kỹ thuật','active'),
            ('Kick-off dự án AI','Phòng A','2026-06-05 09:00','2026-06-05 10:00','Trần Hương','Kỹ thuật','active'),
            ('Họp Marketing Q3','Phòng E','2026-06-06 10:00','2026-06-06 11:00','Phạm Lan','Marketing','active'),
            ('Daily Standup','Phòng B','2026-06-07 08:30','2026-06-07 09:00','Lê Minh','Kỹ thuật','active'),
        ]
        conn.executemany('INSERT INTO meetings (title,room,start_time,end_time,organizer,department,status) VALUES (?,?,?,?,?,?,?)', meetings_data)

        rooms_data = [('Phòng A',20),('Phòng B',15),('Phòng C',10),
                      ('Phòng D',8),('Phòng E',12),('Phòng F',6)]
        conn.executemany('INSERT INTO rooms (name,capacity) VALUES (?,?)', rooms_data)

    conn.commit()
    conn.close()

# ─── ROUTES ──────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('login'))

# ── Auth ─────────────────────────────────────────────────────
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        pw    = hash_pw(request.form['password'])
        user  = q('SELECT * FROM users WHERE email=? AND password=?', (email, pw), one=True)
        if user:
            if user['status'] == 'banned':
                flash('Tài khoản đã bị khoá. Liên hệ Admin.', 'danger')
            else:
                session['user_id']   = user['id']
                session['user_name'] = user['fullname']
                session['role']      = user['role']
                ex('UPDATE users SET last_login=? WHERE id=?',
                   (datetime.now().strftime('%d/%m/%Y %H:%M'), user['id']))
                ex('INSERT INTO activity_logs (user_name,action_type,action,ip,result) VALUES (?,?,?,?,?)',
                   (user['fullname'], 'Đăng nhập', 'Đăng nhập hệ thống', request.remote_addr, 'success'))
                return redirect(url_for('dashboard'))
        else:
            flash('Email hoặc mật khẩu không đúng.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── Dashboard (US-01) ─────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    total_meetings  = q('SELECT COUNT(*) as c FROM meetings', one=True)['c']
    total_users     = q('SELECT COUNT(*) as c FROM users', one=True)['c']
    active_users    = q("SELECT COUNT(*) as c FROM users WHERE status='active'", one=True)['c']
    active_rooms    = q("SELECT COUNT(*) as c FROM rooms WHERE status='active'", one=True)['c']

    # meetings per month (last 6)
    months_data = []
    for i in range(5, -1, -1):
        d = datetime.now() - timedelta(days=30*i)
        m = d.strftime('%Y-%m')
        label = d.strftime('T%m')
        cnt = q("SELECT COUNT(*) as c FROM meetings WHERE start_time LIKE ?", (f'{m}%',), one=True)['c']
        months_data.append({'label': label, 'count': cnt})

    room_stats = q('''SELECT room, COUNT(*) as cnt,
                      ROUND(SUM((strftime('%s',end_time)-strftime('%s',start_time))/3600.0),1) as hrs
                      FROM meetings WHERE status!='cancelled'
                      GROUP BY room ORDER BY hrs DESC LIMIT 6''')

    top_organizers = q('''SELECT organizer, COUNT(*) as cnt FROM meetings
                          GROUP BY organizer ORDER BY cnt DESC LIMIT 4''')

    recent = q('SELECT * FROM meetings ORDER BY created_at DESC LIMIT 5')
    unread = q("SELECT COUNT(*) as c FROM notifications WHERE is_read=0", one=True)['c']

    return render_template('dashboard.html',
        total_meetings=total_meetings, total_users=total_users,
        active_users=active_users, active_rooms=active_rooms,
        months_data=months_data, room_stats=room_stats,
        top_organizers=top_organizers, recent=recent, unread=unread)

# ── Users (US-03) ─────────────────────────────────────────────
@app.route('/users')
@login_required
def users():
    search = request.args.get('search','')
    role   = request.args.get('role','')
    status = request.args.get('status','')
    sql  = 'SELECT * FROM users WHERE 1=1'
    args = []
    if search:
        sql += ' AND (fullname LIKE ? OR email LIKE ?)'
        args += [f'%{search}%', f'%{search}%']
    if role:
        sql += ' AND role=?'; args.append(role)
    if status:
        sql += ' AND status=?'; args.append(status)
    sql += ' ORDER BY created_at DESC'
    data = q(sql, args)
    stats = {
        'total':    q('SELECT COUNT(*) as c FROM users', one=True)['c'],
        'active':   q("SELECT COUNT(*) as c FROM users WHERE status='active'", one=True)['c'],
        'inactive': q("SELECT COUNT(*) as c FROM users WHERE status='inactive'", one=True)['c'],
        'banned':   q("SELECT COUNT(*) as c FROM users WHERE status='banned'", one=True)['c'],
    }
    unread = q("SELECT COUNT(*) as c FROM notifications WHERE is_read=0", one=True)['c']
    return render_template('users.html', users=data, stats=stats,
                           search=search, role=role, status=status, unread=unread)

@app.route('/users/add', methods=['POST'])
@login_required
def add_user():
    fn  = request.form['fullname'].strip()
    em  = request.form['email'].strip()
    rl  = request.form['role']
    try:
        ex('INSERT INTO users (fullname,email,password,role) VALUES (?,?,?,?)',
           (fn, em, hash_pw('123456'), rl))
        ex('INSERT INTO activity_logs (user_name,action_type,action,ip,result) VALUES (?,?,?,?,?)',
           (session['user_name'], 'Quản trị', f'Tạo tài khoản: {em}', request.remote_addr, 'success'))
        flash(f'Đã tạo tài khoản {fn}. Mật khẩu mặc định: 123456', 'success')
    except sqlite3.IntegrityError:
        flash('Email đã tồn tại.', 'danger')
    return redirect(url_for('users'))

@app.route('/users/toggle/<int:uid>')
@login_required
def toggle_user(uid):
    user = q('SELECT * FROM users WHERE id=?', (uid,), one=True)
    if user:
        new_status = 'active' if user['status'] == 'banned' else 'banned'
        ex('UPDATE users SET status=? WHERE id=?', (new_status, uid))
        action = 'Mở khoá' if new_status == 'active' else 'Khoá'
        ex('INSERT INTO activity_logs (user_name,action_type,action,ip,result) VALUES (?,?,?,?,?)',
           (session['user_name'], 'Quản trị', f'{action} tài khoản {user["email"]}', request.remote_addr, 'success'))
        flash(f'Đã {action.lower()} tài khoản {user["fullname"]}.', 'success')
    return redirect(url_for('users'))

@app.route('/users/edit/<int:uid>', methods=['POST'])
@login_required
def edit_user(uid):
    fn = request.form['fullname'].strip()
    rl = request.form['role']
    st = request.form['status']
    ex('UPDATE users SET fullname=?,role=?,status=? WHERE id=?', (fn, rl, st, uid))
    flash('Đã cập nhật tài khoản.', 'success')
    return redirect(url_for('users'))

# ── Permissions (US-04) ───────────────────────────────────────
@app.route('/permissions')
@login_required
def permissions():
    role = request.args.get('role','admin')
    perms = q('SELECT * FROM permissions WHERE role_name=? ORDER BY perm_group,perm_name', (role,))
    groups = {}
    for p in perms:
        groups.setdefault(p['perm_group'], []).append(p)
    role_info = q('SELECT * FROM roles WHERE name=?', (role,), one=True)
    role_users = q('SELECT COUNT(*) as c FROM users WHERE role=?', (role,), one=True)['c']
    sample_users = q('SELECT fullname,email FROM users WHERE role=? LIMIT 3', (role,))
    all_roles = q('SELECT * FROM roles')
    unread = q("SELECT COUNT(*) as c FROM notifications WHERE is_read=0", one=True)['c']
    return render_template('permissions.html',
        groups=groups, role=role, role_info=role_info,
        role_users=role_users, sample_users=sample_users,
        all_roles=all_roles, unread=unread)

@app.route('/permissions/toggle/<int:pid>')
@login_required
def toggle_perm(pid):
    p = q('SELECT * FROM permissions WHERE id=?', (pid,), one=True)
    if p:
        ex('UPDATE permissions SET enabled=? WHERE id=?', (0 if p['enabled'] else 1, pid))
    role = request.args.get('role','admin')
    return redirect(url_for('permissions', role=role))

@app.route('/permissions/save', methods=['POST'])
@login_required
def save_permissions():
    role = request.form.get('role','admin')
    perms = q('SELECT id FROM permissions WHERE role_name=?', (role,))
    for p in perms:
        val = 1 if request.form.get(f'perm_{p["id"]}') else 0
        ex('UPDATE permissions SET enabled=? WHERE id=?', (val, p['id']))
    ex('INSERT INTO activity_logs (user_name,action_type,action,ip,result) VALUES (?,?,?,?,?)',
       (session['user_name'], 'Quản trị', f'Cập nhật quyền vai trò {role}', request.remote_addr, 'success'))
    flash('Đã lưu quyền thành công.', 'success')
    return redirect(url_for('permissions', role=role))

# ── Notifications (US-05) ─────────────────────────────────────
@app.route('/notifications')
@login_required
def notifications():
    unread_list  = q("SELECT * FROM notifications WHERE is_read=0 ORDER BY created_at DESC")
    read_list    = q("SELECT * FROM notifications WHERE is_read=1 ORDER BY created_at DESC LIMIT 20")
    unread_count = len(unread_list)
    unread_nb    = unread_count   # for base.html sidebar badge
    return render_template('notifications.html',
        notif_unread=unread_list, notif_read=read_list,
        unread_count=unread_count, unread=unread_nb)

@app.route('/notifications/mark_all')
@login_required
def mark_all_read():
    ex('UPDATE notifications SET is_read=1')
    flash('Đã đánh dấu tất cả là đã đọc.', 'success')
    return redirect(url_for('notifications'))

@app.route('/notifications/read/<int:nid>')
@login_required
def mark_read(nid):
    ex('UPDATE notifications SET is_read=1 WHERE id=?', (nid,))
    return redirect(url_for('notifications'))

# ── Activity Logs (US-06) ─────────────────────────────────────
@app.route('/logs')
@login_required
def logs():
    filter_type = request.args.get('type','')
    search      = request.args.get('search','')
    sql  = 'SELECT * FROM activity_logs WHERE 1=1'
    args = []
    if filter_type and filter_type != 'Tất cả':
        sql += ' AND action_type=?'; args.append(filter_type)
    if search:
        sql += ' AND (user_name LIKE ? OR action LIKE ? OR ip LIKE ?)'
        args += [f'%{search}%']*3
    sql += ' ORDER BY created_at DESC LIMIT 100'
    data = q(sql, args)
    stats = {
        'total':   q('SELECT COUNT(*) as c FROM activity_logs WHERE DATE(created_at)=DATE("now","localtime")', one=True)['c'],
        'success': q("SELECT COUNT(*) as c FROM activity_logs WHERE result='success' AND DATE(created_at)=DATE('now','localtime')", one=True)['c'],
        'failed':  q("SELECT COUNT(*) as c FROM activity_logs WHERE result='failed' AND DATE(created_at)=DATE('now','localtime')", one=True)['c'],
        'admin':   q("SELECT COUNT(*) as c FROM activity_logs WHERE action_type='Quản trị' AND DATE(created_at)=DATE('now','localtime')", one=True)['c'],
    }
    types = ['Tất cả','Đăng nhập','Quản trị','Lịch họp','Bảo mật','Lỗi']
    unread = q("SELECT COUNT(*) as c FROM notifications WHERE is_read=0", one=True)['c']
    return render_template('logs.html', logs=data, stats=stats,
                           types=types, filter_type=filter_type, search=search, unread=unread)

# ── Reports (US-02) ───────────────────────────────────────────
@app.route('/reports')
@login_required
def reports():
    total_m  = q('SELECT COUNT(*) as c FROM meetings', one=True)['c']
    cancelled= q("SELECT COUNT(*) as c FROM meetings WHERE status='cancelled'", one=True)['c']
    cancel_rate = round(cancelled/total_m*100,1) if total_m else 0

    room_stats = q('''SELECT room,
                      COUNT(*) as cnt,
                      ROUND(SUM((strftime('%s',end_time)-strftime('%s',start_time))/3600.0),1) as hrs
                      FROM meetings WHERE status!='cancelled'
                      GROUP BY room ORDER BY hrs DESC''')

    dept_stats = q('''SELECT department, COUNT(*) as cnt,
                      ROUND(SUM((strftime('%s',end_time)-strftime('%s',start_time))/3600.0),1) as hrs
                      FROM meetings GROUP BY department ORDER BY cnt DESC LIMIT 5''')

    max_cnt = dept_stats[0]['cnt'] if dept_stats else 1
    unread = q("SELECT COUNT(*) as c FROM notifications WHERE is_read=0", one=True)['c']
    return render_template('reports.html',
        total_m=total_m, cancel_rate=cancel_rate,
        room_stats=room_stats, dept_stats=dept_stats,
        max_cnt=max_cnt, unread=unread)

# ── Settings (US-07) ─────────────────────────────────────────
@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    if request.method == 'POST':
        for key, val in request.form.items():
            ex('INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)', (key, val))
        # checkboxes that may be absent
        for cb in ['notify_reminder','notify_email','notify_app','two_fa','auto_backup','smtp_ssl']:
            ex('INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)',
               (cb, '1' if cb in request.form else '0'))
        ex('INSERT INTO activity_logs (user_name,action_type,action,ip,result) VALUES (?,?,?,?,?)',
           (session['user_name'], 'Quản trị', 'Cập nhật cài đặt hệ thống', request.remote_addr, 'success'))
        flash('Đã lưu cài đặt thành công.', 'success')
        return redirect(url_for('settings'))

    rows = q('SELECT * FROM settings')
    cfg  = {r['key']: r['value'] for r in rows}
    unread = q("SELECT COUNT(*) as c FROM notifications WHERE is_read=0", one=True)['c']
    return render_template('settings.html', cfg=cfg, unread=unread)

@app.route('/settings/reset')
@login_required
def reset_settings():
    ex('DELETE FROM settings')
    flash('Đã khôi phục cài đặt mặc định. Khởi động lại ứng dụng để áp dụng.', 'warning')
    return redirect(url_for('settings'))

app.jinja_env.globals.update(enumerate=enumerate,
                             now=datetime.now().strftime('%m/%Y'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
