import os
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3
import datetime
import requests
import json
import pdfplumber
from flask import Flask, render_template, url_for, session, redirect, request
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from groq import Groq
from pypdf import PdfReader
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# -----------------------------------------------------------
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super_secret_dev_key")
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# Login Setup
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

client = Groq(api_key=os.getenv("GROK_API_KEY"))

# --- HELPER FUNCTIONS ---

def get_db_connection():
    """Smart connection: Postgres (Render) or SQLite (Local)"""
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        return conn
    else:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """Create ALL tables automatically"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Check if Postgres (Render)
    if os.environ.get('DATABASE_URL'):
        # 1. Users Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                picture TEXT,
                role TEXT,
                last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                login_count INTEGER DEFAULT 1
            )
        ''')
        # 2. Reports Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY,
                user_email TEXT,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 3. Saved Jobs Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS saved_jobs (
                id SERIAL PRIMARY KEY,
                user_email TEXT,
                title TEXT,
                company TEXT,
                location TEXT,
                url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 4. Job Cache Table
        c.execute('''
            CREATE TABLE IF NOT EXISTS job_cache (
                search_key TEXT PRIMARY KEY,
                json_data TEXT,
                updated_at TEXT
            )
        ''')
    else:
        # SQLite Versions
        c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, name TEXT, picture TEXT, role TEXT, last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP, login_count INTEGER DEFAULT 1)')
        c.execute('CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, role TEXT, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        c.execute('CREATE TABLE IF NOT EXISTS saved_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, title TEXT, company TEXT, location TEXT, url TEXT, created_at TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS job_cache (search_key TEXT PRIMARY KEY, json_data TEXT, updated_at TEXT)')

    conn.commit()
    conn.close()
    print("Database Initialized Successfully.")

def extract_text_from_pdf(file):
    try:
        with pdfplumber.open(file) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            return text
    except Exception as e:
        return ""

# --- RUN DB INIT ON STARTUP ---
with app.app_context():
    init_db()

# --- ROUTES ---

@app.route('/')
def home():
    if 'user' in session:
        conn = get_db_connection()
        c = conn.cursor()
        email = session['user']['email']
        
        # Determine query syntax based on DB type
        if os.environ.get('DATABASE_URL'):
            # Postgres Syntax (%s)
            c.execute("SELECT * FROM reports WHERE user_email = %s ORDER BY id DESC LIMIT 3", (email,))
            saved_reports = c.fetchall()
            
            c.execute("SELECT * FROM saved_jobs WHERE user_email = %s ORDER BY id DESC LIMIT 5", (email,))
            saved_jobs_list = c.fetchall()
        else:
            # SQLite Syntax (?)
            c.execute("SELECT * FROM reports WHERE user_email = ? ORDER BY id DESC LIMIT 3", (email,))
            saved_reports = c.fetchall()
            
            c.execute("SELECT * FROM saved_jobs WHERE user_email = ? ORDER BY id DESC LIMIT 5", (email,))
            saved_jobs_list = c.fetchall()
        
        conn.close()
        
        # Convert RealDictRow to list if needed (Postgres returns RealDictRow which is fine for Jinja)
        return render_template('dashboard.html', user=session['user'], reports=saved_reports, saved_jobs=saved_jobs_list)
        
    return render_template('login.html')

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/google/callback')
def authorize():
    token = google.authorize_access_token()
    user_info = google.get('https://www.googleapis.com/oauth2/v1/userinfo').json()
    session['user'] = user_info
    
    email = user_info['email']
    name = user_info.get('name', 'User')
    picture = user_info.get('picture', '')

    conn = get_db_connection()
    c = conn.cursor()
    
    is_postgres = os.environ.get('DATABASE_URL') is not None

    if is_postgres:
        c.execute("SELECT * FROM users WHERE email = %s", (email,))
    else:
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        
    existing_user = c.fetchone()

    if not existing_user:
        if is_postgres:
            c.execute("INSERT INTO users (email, name, picture, role, login_count, last_login) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)", 
                     (email, name, picture, 'Student', 1))
        else:
            c.execute("INSERT INTO users (email, name, picture, role, login_count, last_login) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", 
                     (email, name, picture, 'Student', 1))
    else:
        # Access column safely
        current_count = existing_user['login_count'] if existing_user else 0
        new_count = current_count + 1
        
        if is_postgres:
            c.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP, login_count = %s, picture = %s WHERE email = %s", 
                     (new_count, picture, email))
        else:
            c.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP, login_count = ?, picture = ? WHERE email = ?", 
                     (new_count, picture, email))

    conn.commit()
    conn.close()
    
    return redirect('/')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# --- MODULES (Keep these simple) ---

@app.route('/resume')
def resume_module():
    if 'user' not in session: return redirect('/')
    return render_template('resume.html')

@app.route('/resume/analyze', methods=['POST'])
def analyze_resume():
    if 'user' not in session: return redirect('/')
    if 'resume' not in request.files: return "No file uploaded", 400
    file = request.files['resume']
    target_role = request.form.get('job_role')
    text = extract_text_from_pdf(file)
    if len(text) < 50: return "Resume is too short or unreadable.", 400

    prompt = f"Analyze resume for {target_role}. Content: {text[:3000]}. Give HTML output."
    
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant" 
        )
        content = completion.choices[0].message.content.replace("```html", "").replace("```", "")
        
        # Save Report
        conn = get_db_connection()
        c = conn.cursor()
        
        if os.environ.get('DATABASE_URL'):
            c.execute("INSERT INTO reports (user_email, role, content, created_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP)", 
                     (session['user']['email'], target_role, content))
        else:
            now = datetime.datetime.now().strftime("%Y-%m-%d")
            c.execute("INSERT INTO reports (user_email, role, content, created_at) VALUES (?, ?, ?, ?)", 
                     (session['user']['email'], target_role, content, now))
        
        conn.commit()
        conn.close()
        
        return render_template('resume_result.html', analysis=content)
    except Exception as e:
        return f"AI Error: {e}"

@app.route('/report/<int:report_id>')
def view_report(report_id):
    if 'user' not in session: return redirect('/')
    conn = get_db_connection()
    c = conn.cursor()
    
    if os.environ.get('DATABASE_URL'):
        c.execute("SELECT * FROM reports WHERE id = %s", (report_id,))
    else:
        c.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        
    report = c.fetchone()
    conn.close()
    
    if report:
        return render_template('resume_result.html', analysis=report['content'])
    else:
        return "Report not found", 404

@app.route('/chatbot')
def interview_module():
    if 'user' not in session: return redirect('/')
    return render_template('interview.html')

@app.route('/interview/generate', methods=['POST'])
def generate_interview_questions():
    if 'user' not in session: return "Unauthorized", 401
    # ... (Your existing logic is fine here, assuming no DB writes) ...
    # Simplified for brevity - ensure you keep your AI logic
    return "AI Response" 

@app.route('/jobs')
def job_search_module():
    if 'user' not in session: return redirect('/')
    return render_template('jobs.html')

@app.route('/jobs/search', methods=['POST'])
def search_jobs():
    if 'user' not in session: return "Unauthorized", 401
    role = request.form.get('role')
    location = request.form.get('location')
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # ... (Your Adzuna logic here) ...
    # Ensure you use 'conn' from get_db_connection()
    
    return "Job HTML"

@app.route('/jobs/save', methods=['POST'])
def save_job():
    if 'user' not in session: return "Unauthorized", 401
    data = request.json
    
    conn = get_db_connection()
    c = conn.cursor()
    email = session['user']['email']
    
    is_postgres = os.environ.get('DATABASE_URL') is not None
    
    if is_postgres:
        c.execute("SELECT id FROM saved_jobs WHERE user_email = %s AND url = %s", (email, data['url']))
        if c.fetchone(): return "Already saved", 200
        c.execute("INSERT INTO saved_jobs (user_email, title, company, location, url, created_at) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)", 
                 (email, data['title'], data['company'], data['location'], data['url']))
    else:
        c.execute("SELECT id FROM saved_jobs WHERE user_email = ? AND url = ?", (email, data['url']))
        if c.fetchone(): return "Already saved", 200
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        c.execute("INSERT INTO saved_jobs (user_email, title, company, location, url, created_at) VALUES (?, ?, ?, ?, ?, ?)", 
                 (email, data['title'], data['company'], data['location'], data['url'], now))
                 
    conn.commit()
    conn.close()
    return "Saved", 200

@app.route('/courses')
def course_module():
    if 'user' not in session: return redirect('/')
    return render_template('courses.html')

@app.route('/admin')
def admin_panel():
    if 'user' not in session: return redirect('/')
    admin_email = 'mehvishsheikh.3101@gmail.com' 
    if session['user']['email'] != admin_email: return "Forbidden", 403

    conn = get_db_connection()
    c = conn.cursor()
    
    if os.environ.get('DATABASE_URL'):
        c.execute("SELECT * FROM users ORDER BY last_login DESC")
        users = c.fetchall()
        c.execute("SELECT COUNT(*) FROM reports")
        res = c.fetchone()
        # RealDictCursor returns dictionary, e.g. {'count': 5}
        total_scans = res['count'] if res else 0
    else:
        c.execute("SELECT * FROM users ORDER BY last_login DESC")
        users = c.fetchall()
        c.execute("SELECT COUNT(*) FROM reports")
        total_scans = c.fetchone()[0]
    
    conn.close()
    return render_template('admin.html', users=users, total_users=len(users), total_scans=total_scans)

# --- DB FIX ROUTE (Optional) ---
@app.route('/fix-db')
def fix_db_manual():
    init_db()
    return "Database Tables Created Manually!"

# --- RESET REPORTS TABLE ---
# --- EMERGENCY DB RESET ROUTE ---
@app.route('/nuclear-reset')
def nuclear_reset():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. DELETE ALL OLD TABLES (Force Clean Slate)
    # This fixes "Column not found" and "Relation does not exist" errors
    c.execute("DROP TABLE IF EXISTS reports")
    c.execute("DROP TABLE IF EXISTS saved_jobs")
    c.execute("DROP TABLE IF EXISTS job_cache")
    c.execute("DROP TABLE IF EXISTS users") 
    
    conn.commit()
    conn.close()
    
    # 2. CREATE FRESH TABLES
    init_db()
    
    return "<h1>DATABASE RESET SUCCESSFUL. All tables are fixed. You can now Log In.</h1>"
if __name__ == '__main__':
    app.run(debug=True)