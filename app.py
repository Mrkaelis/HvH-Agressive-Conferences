import os, sqlite3, secrets
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'hvh.db')
UPLOAD_AVATARS = os.path.join(BASE, 'static', 'uploads', 'avatars')
UPLOAD_CONFIGS = os.path.join(BASE, 'static', 'uploads', 'configs')
os.makedirs(UPLOAD_AVATARS, exist_ok=True)
os.makedirs(UPLOAD_CONFIGS, exist_ok=True)

ADMIN_PASSWORD = '123wue123'
DEFAULT_ADMIN_EMAIL = 'dimacontrol2223@gmail.com'

app = Flask(__name__)
app.secret_key = 'hvh-agressive-conference-secret-key-change-me'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    c = db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password TEXT NOT NULL,
        avatar TEXT DEFAULT '',
        rating INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS admin_emails(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS about(id INTEGER PRIMARY KEY CHECK(id=1), content TEXT);
    CREATE TABLE IF NOT EXISTS welcome(id INTEGER PRIMARY KEY CHECK(id=1), content TEXT);
    CREATE TABLE IF NOT EXISTS championship(
        id INTEGER PRIMARY KEY CHECK(id=1),
        title TEXT, date TEXT, description TEXT
    );
    CREATE TABLE IF NOT EXISTS championship_players(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id)
    );
    CREATE TABLE IF NOT EXISTS configs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, description TEXT, price INTEGER NOT NULL,
        filename TEXT, seller_id INTEGER, approved INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS purchases(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, config_id INTEGER NOT NULL,
        price INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, username TEXT, text TEXT NOT NULL,
        rating INTEGER DEFAULT 5, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS keys(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL, amount INTEGER NOT NULL,
        used_by INTEGER, used_at DATETIME
    );
    ''')
    c.execute("INSERT OR IGNORE INTO welcome(id,content) VALUES(1,?)",
              ("Добро пожаловать в HvH Agressive Conference — комьюнити самых агрессивных HvH игроков. Здесь ты найдёшь топовых людей сцены, эксклюзивные конфиги и место, где твой скилл имеет значение.",))
    c.execute("INSERT OR IGNORE INTO about(id,content) VALUES(1,?)",
              ("HvH (Hack vs Hack) — противостояние читеров, где побеждает не рука, а мозг. HvH Agressive Conference — сообщество, где обсуждают конфиги, resolver'ы, anti-aim'ы и всё, что делает игру по-настоящему агрессивной.",))
    c.execute("INSERT OR IGNORE INTO championship(id,title,date,description) VALUES(1,?,?,?)",
              ("HvH Agressive Championship #1", "", "Регистрация открыта. Нажми кнопку «Зарегистрироваться», чтобы попасть в сетку.",))
    c.execute("INSERT OR IGNORE INTO admin_emails(email) VALUES(?)", (DEFAULT_ADMIN_EMAIL,))
    # sync is_admin flag for existing users whose email is in admin_emails
    c.execute("""UPDATE users SET is_admin=1 WHERE email IN (SELECT email FROM admin_emails)""")
    c.commit(); c.close()

init_db()

def is_admin_email(email):
    if not email: return False
    c = db()
    r = c.execute("SELECT 1 FROM admin_emails WHERE lower(email)=lower(?)", (email,)).fetchone()
    c.close()
    return bool(r)

def current_user():
    uid = session.get('uid')
    if not uid: return None
    c = db(); u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(); c.close()
    return u

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get('uid'): return redirect(url_for('login'))
        return f(*a, **k)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if session.get('admin'): return f(*a, **k)
        u = current_user()
        if u and u['is_admin']: return f(*a, **k)
        return redirect(url_for('admin_login'))
    return w

@app.context_processor
def inject():
    u = current_user()
    return {
        'user': u,
        'is_admin_user': bool(session.get('admin') or (u and u['is_admin'])),
        'site_name': 'HvH Agressive Conference'
    }

# --- Public ---
@app.route('/')
def index():
    c = db()
    w = c.execute("SELECT content FROM welcome WHERE id=1").fetchone()
    top = c.execute("SELECT username, avatar, rating FROM users ORDER BY rating DESC LIMIT 5").fetchall()
    ch = c.execute("SELECT * FROM championship WHERE id=1").fetchone()
    c.close()
    return render_template('index.html', welcome=w['content'] if w else '', top=top, ch=ch)

@app.route('/rating')
def rating():
    c = db()
    users = c.execute("SELECT username, avatar, rating FROM users ORDER BY rating DESC").fetchall()
    c.close()
    return render_template('rating.html', users=users)

@app.route('/about')
def about():
    c = db(); a = c.execute("SELECT content FROM about WHERE id=1").fetchone(); c.close()
    return render_template('about.html', content=a['content'] if a else '')

@app.route('/championship', methods=['GET','POST'])
def championship():
    u = current_user()
    c = db()
    if request.method == 'POST':
        if not u: c.close(); return redirect(url_for('login'))
        try:
            c.execute("INSERT INTO championship_players(user_id) VALUES(?)", (u['id'],))
            c.commit()
            flash('Ты в сетке! Ждём остальных.', 'ok')
        except sqlite3.IntegrityError:
            flash('Ты уже зарегистрирован','err')
    ch = c.execute("SELECT * FROM championship WHERE id=1").fetchone()
    players = c.execute("""SELECT u.username,u.avatar,u.rating FROM championship_players p
                           JOIN users u ON u.id=p.user_id ORDER BY u.rating DESC""").fetchall()
    registered = False
    if u:
        registered = bool(c.execute("SELECT 1 FROM championship_players WHERE user_id=?", (u['id'],)).fetchone())
    c.close()
    # build simple bracket pairs
    pairs = [(players[i], players[i+1] if i+1 < len(players) else None) for i in range(0, len(players), 2)]
    return render_template('championship.html', ch=ch, players=players, pairs=pairs, registered=registered)

@app.route('/configs')
def configs():
    c = db()
    items = c.execute("""SELECT c.*, u.username as seller FROM configs c
                         LEFT JOIN users u ON u.id=c.seller_id
                         WHERE c.approved=1 ORDER BY c.created_at DESC""").fetchall()
    c.close()
    return render_template('configs.html', items=items)

@app.route('/buy/<int:cid>', methods=['POST'])
@login_required
def buy(cid):
    u = current_user()
    c = db()
    cfg = c.execute("SELECT * FROM configs WHERE id=? AND approved=1", (cid,)).fetchone()
    if not cfg:
        c.close(); flash('Конфиг не найден','err'); return redirect(url_for('configs'))
    if cfg['seller_id'] == u['id']:
        c.close(); flash('Нельзя купить свой конфиг','err'); return redirect(url_for('configs'))
    if u['balance'] < cfg['price']:
        c.close(); flash('Недостаточно баланса','err'); return redirect(url_for('configs'))
    c.execute("UPDATE users SET balance=balance-? WHERE id=?", (cfg['price'], u['id']))
    if cfg['seller_id']:
        c.execute("UPDATE users SET balance=balance+? WHERE id=?", (cfg['price'], cfg['seller_id']))
    c.execute("INSERT INTO purchases(user_id,config_id,price) VALUES(?,?,?)", (u['id'], cid, cfg['price']))
    c.commit(); c.close()
    flash('Куплено! Скачивай в личном кабинете.','ok')
    return redirect(url_for('cabinet'))

@app.route('/download/<int:cid>')
@login_required
def download(cid):
    u = current_user()
    c = db()
    p = c.execute("SELECT * FROM purchases WHERE user_id=? AND config_id=?", (u['id'], cid)).fetchone()
    cfg = c.execute("SELECT * FROM configs WHERE id=?", (cid,)).fetchone()
    c.close()
    if not p and (not cfg or cfg['seller_id'] != u['id']): abort(403)
    if not cfg or not cfg['filename']: abort(404)
    return send_from_directory(UPLOAD_CONFIGS, cfg['filename'], as_attachment=True)

@app.route('/reviews', methods=['GET','POST'])
def reviews():
    c = db()
    if request.method == 'POST':
        u = current_user()
        if not u: c.close(); return redirect(url_for('login'))
        text = request.form.get('text','').strip()[:1000]
        r = max(1, min(5, int(request.form.get('rating',5) or 5)))
        if text:
            c.execute("INSERT INTO reviews(user_id,username,text,rating) VALUES(?,?,?,?)",
                      (u['id'], u['username'], text, r))
            c.commit()
    items = c.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
    c.close()
    return render_template('reviews.html', items=items)

# --- Auth ---
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        un = request.form.get('username','').strip()[:32]
        em = request.form.get('email','').strip().lower()[:120]
        pw = request.form.get('password','')
        if len(un) < 3 or len(pw) < 4 or '@' not in em:
            flash('Логин ≥3, пароль ≥4, корректный email','err')
        else:
            try:
                c = db()
                admin_flag = 1 if is_admin_email(em) else 0
                c.execute("INSERT INTO users(username,email,password,is_admin) VALUES(?,?,?,?)",
                          (un, em, generate_password_hash(pw), admin_flag))
                c.commit(); c.close()
                flash('Регистрация успешна, войди','ok')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Логин или email заняты','err')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        un = request.form.get('username','').strip()
        pw = request.form.get('password','')
        c = db(); u = c.execute("SELECT * FROM users WHERE username=? OR email=?", (un, un.lower())).fetchone(); c.close()
        if u and check_password_hash(u['password'], pw):
            session['uid'] = u['id']
            # refresh admin flag if email in admin list
            if u['email'] and is_admin_email(u['email']) and not u['is_admin']:
                c = db(); c.execute("UPDATE users SET is_admin=1 WHERE id=?", (u['id'],)); c.commit(); c.close()
            return redirect(url_for('cabinet'))
        flash('Неверный логин или пароль','err')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('uid', None); session.pop('admin', None)
    return redirect(url_for('index'))

# --- Cabinet ---
@app.route('/cabinet')
@login_required
def cabinet():
    u = current_user()
    c = db()
    place = c.execute("SELECT COUNT(*)+1 as p FROM users WHERE rating > ?", (u['rating'],)).fetchone()['p']
    top = c.execute("SELECT username,avatar,rating FROM users ORDER BY rating DESC LIMIT 5").fetchall()
    my_configs = c.execute("SELECT * FROM configs WHERE seller_id=? ORDER BY created_at DESC", (u['id'],)).fetchall()
    purchased = c.execute("""SELECT c.* FROM purchases p JOIN configs c ON c.id=p.config_id
                             WHERE p.user_id=? ORDER BY p.created_at DESC""", (u['id'],)).fetchall()
    c.close()
    return render_template('cabinet.html', me=u, place=place, top=top,
                           my_configs=my_configs, purchased=purchased)

@app.route('/cabinet/sell', methods=['POST'])
@login_required
def sell_config():
    u = current_user()
    title = request.form.get('title','').strip()[:80]
    desc = request.form.get('description','').strip()[:500]
    try: price = max(0, int(request.form.get('price',0)))
    except: price = 0
    f = request.files.get('file')
    if not title or not f or not f.filename:
        flash('Заполни поля и прикрепи файл','err'); return redirect(url_for('cabinet'))
    fn = secure_filename(f"{secrets.token_hex(6)}_{f.filename}")
    f.save(os.path.join(UPLOAD_CONFIGS, fn))
    c = db()
    c.execute("INSERT INTO configs(title,description,price,filename,seller_id,approved) VALUES(?,?,?,?,?,1)",
              (title, desc, price, fn, u['id']))
    c.commit(); c.close()
    flash('Конфиг выставлен на продажу','ok')
    return redirect(url_for('cabinet'))

@app.route('/cabinet/redeem', methods=['POST'])
@login_required
def redeem():
    code = request.form.get('code','').strip()
    u = current_user()
    c = db()
    k = c.execute("SELECT * FROM keys WHERE code=? AND used_by IS NULL", (code,)).fetchone()
    if not k:
        c.close(); flash('Ключ недействителен или уже использован','err')
        return redirect(url_for('cabinet'))
    c.execute("UPDATE keys SET used_by=?, used_at=CURRENT_TIMESTAMP WHERE id=?", (u['id'], k['id']))
    c.execute("UPDATE users SET balance=balance+? WHERE id=?", (k['amount'], u['id']))
    c.commit(); c.close()
    flash(f'Баланс пополнен на {k["amount"]}₽','ok')
    return redirect(url_for('cabinet'))

@app.route('/cabinet/avatar', methods=['POST'])
@login_required
def cab_avatar():
    u = current_user()
    f = request.files.get('avatar')
    if f and f.filename:
        fn = secure_filename(f"{u['id']}_{secrets.token_hex(4)}_{f.filename}")
        f.save(os.path.join(UPLOAD_AVATARS, fn))
        c = db(); c.execute("UPDATE users SET avatar=? WHERE id=?", (fn, u['id'])); c.commit(); c.close()
        flash('Аватар обновлён','ok')
    return redirect(url_for('cabinet'))

# --- Admin ---
@app.route('/admin', methods=['GET','POST'])
def admin_login():
    if session.get('admin'): return redirect(url_for('admin_panel'))
    u = current_user()
    if u and u['is_admin']: return redirect(url_for('admin_panel'))
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        flash('Неверный пароль','err')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None); return redirect(url_for('index'))

@app.route('/admin/panel')
@admin_required
def admin_panel():
    c = db()
    users = c.execute("SELECT * FROM users ORDER BY rating DESC").fetchall()
    configs = c.execute("SELECT c.*, u.username as seller FROM configs c LEFT JOIN users u ON u.id=c.seller_id ORDER BY c.created_at DESC").fetchall()
    reviews = c.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
    keys = c.execute("SELECT k.*, u.username as user FROM keys k LEFT JOIN users u ON u.id=k.used_by ORDER BY k.id DESC").fetchall()
    welcome = c.execute("SELECT content FROM welcome WHERE id=1").fetchone()['content']
    about = c.execute("SELECT content FROM about WHERE id=1").fetchone()['content']
    ch = c.execute("SELECT * FROM championship WHERE id=1").fetchone()
    ch_players = c.execute("""SELECT p.id as pid, u.username FROM championship_players p
                              JOIN users u ON u.id=p.user_id ORDER BY u.rating DESC""").fetchall()
    admin_emails = c.execute("SELECT * FROM admin_emails ORDER BY id").fetchall()
    c.close()
    return render_template('admin_panel.html', users=users, configs=configs,
                           reviews=reviews, keys=keys, welcome=welcome, about=about,
                           ch=ch, ch_players=ch_players, admin_emails=admin_emails)

@app.route('/admin/text', methods=['POST'])
@admin_required
def admin_text():
    c = db()
    c.execute("UPDATE welcome SET content=? WHERE id=1", (request.form.get('welcome',''),))
    c.execute("UPDATE about SET content=? WHERE id=1", (request.form.get('about',''),))
    c.commit(); c.close()
    flash('Тексты обновлены','ok'); return redirect(url_for('admin_panel'))

@app.route('/admin/championship', methods=['POST'])
@admin_required
def admin_championship():
    c = db()
    c.execute("UPDATE championship SET title=?, date=?, description=? WHERE id=1",
              (request.form.get('title',''), request.form.get('date',''), request.form.get('description','')))
    c.commit(); c.close()
    flash('Чемпионат обновлён','ok'); return redirect(url_for('admin_panel'))

@app.route('/admin/championship/clear', methods=['POST'])
@admin_required
def admin_ch_clear():
    c = db(); c.execute("DELETE FROM championship_players"); c.commit(); c.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/championship/kick/<int:pid>', methods=['POST'])
@admin_required
def admin_ch_kick(pid):
    c = db(); c.execute("DELETE FROM championship_players WHERE id=?", (pid,)); c.commit(); c.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/user/<int:uid>', methods=['POST'])
@admin_required
def admin_user(uid):
    action = request.form.get('action')
    c = db()
    if action == 'rating':
        c.execute("UPDATE users SET rating=? WHERE id=?", (int(request.form.get('rating',0)), uid))
    elif action == 'balance':
        c.execute("UPDATE users SET balance=? WHERE id=?", (int(request.form.get('balance',0)), uid))
    elif action == 'avatar':
        f = request.files.get('avatar')
        if f and f.filename:
            fn = secure_filename(f"{uid}_{secrets.token_hex(4)}_{f.filename}")
            f.save(os.path.join(UPLOAD_AVATARS, fn))
            c.execute("UPDATE users SET avatar=? WHERE id=?", (fn, uid))
    elif action == 'toggle_admin':
        cur = c.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
        c.execute("UPDATE users SET is_admin=? WHERE id=?", (0 if cur['is_admin'] else 1, uid))
    elif action == 'delete':
        c.execute("DELETE FROM users WHERE id=?", (uid,))
    c.commit(); c.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/emails/add', methods=['POST'])
@admin_required
def admin_email_add():
    em = request.form.get('email','').strip().lower()
    if '@' in em:
        c = db()
        try:
            c.execute("INSERT INTO admin_emails(email) VALUES(?)", (em,))
            c.execute("UPDATE users SET is_admin=1 WHERE lower(email)=?", (em,))
            c.commit()
            flash(f'{em} добавлен в админы','ok')
        except sqlite3.IntegrityError:
            flash('Email уже в списке','err')
        c.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/emails/<int:eid>/delete', methods=['POST'])
@admin_required
def admin_email_del(eid):
    c = db()
    row = c.execute("SELECT email FROM admin_emails WHERE id=?", (eid,)).fetchone()
    if row and row['email'].lower() != DEFAULT_ADMIN_EMAIL.lower():
        c.execute("DELETE FROM admin_emails WHERE id=?", (eid,))
        c.execute("UPDATE users SET is_admin=0 WHERE lower(email)=?", (row['email'].lower(),))
        c.commit()
    c.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/config/new', methods=['POST'])
@admin_required
def admin_config_new():
    title = request.form.get('title','').strip()[:80]
    desc = request.form.get('description','').strip()[:500]
    try: price = max(0, int(request.form.get('price',0)))
    except: price = 0
    f = request.files.get('file')
    if not title or not f or not f.filename:
        flash('Заполни поля','err'); return redirect(url_for('admin_panel'))
    fn = secure_filename(f"admin_{secrets.token_hex(6)}_{f.filename}")
    f.save(os.path.join(UPLOAD_CONFIGS, fn))
    c = db()
    c.execute("INSERT INTO configs(title,description,price,filename,seller_id,approved) VALUES(?,?,?,?,NULL,1)",
              (title, desc, price, fn))
    c.commit(); c.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/config/<int:cid>/delete', methods=['POST'])
@admin_required
def admin_config_del(cid):
    c = db(); c.execute("DELETE FROM configs WHERE id=?", (cid,)); c.commit(); c.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/review/<int:rid>/delete', methods=['POST'])
@admin_required
def admin_review_del(rid):
    c = db(); c.execute("DELETE FROM reviews WHERE id=?", (rid,)); c.commit(); c.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/key/new', methods=['POST'])
@admin_required
def admin_key_new():
    try: amount = max(1, int(request.form.get('amount',0)))
    except: amount = 0
    count = max(1, min(100, int(request.form.get('count',1) or 1)))
    c = db()
    for _ in range(count):
        code = 'HVH-' + secrets.token_urlsafe(10).upper().replace('_','').replace('-','')[:14]
        c.execute("INSERT INTO keys(code,amount) VALUES(?,?)", (code, amount))
    c.commit(); c.close()
    flash(f'Создано ключей: {count}','ok')
    return redirect(url_for('admin_panel'))

@app.route('/admin/key/<int:kid>/delete', methods=['POST'])
@admin_required
def admin_key_del(kid):
    c = db(); c.execute("DELETE FROM keys WHERE id=? AND used_by IS NULL", (kid,)); c.commit(); c.close()
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
