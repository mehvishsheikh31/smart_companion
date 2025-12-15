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
# Fix for Render's Proxy headers (prevents HTTP/HTTPS mismatch errors)
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

# AI Client
client = Groq(api_key=os.getenv("GROK_API_KEY")) # Ensure this matches your .env

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
            
            # Use Try/Except to handle case if table was missing momentarily
            try:
                c.execute("SELECT * FROM saved_jobs WHERE user_email = %s ORDER BY id DESC LIMIT 5", (email,))
                saved_jobs_list = c.fetchall()
            except:
                saved_jobs_list = []
        else:
            # SQLite Syntax (?)
            c.execute("SELECT * FROM reports WHERE user_email = ? ORDER BY id DESC LIMIT 3", (email,))
            saved_reports = c.fetchall()
            
            try:
                c.execute("SELECT * FROM saved_jobs WHERE user_email = ? ORDER BY id DESC LIMIT 5", (email,))
                saved_jobs_list = c.fetchall()
            except:
                saved_jobs_list = []
        
        conn.close()
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

# --- MODULE 1: RESUME (High Quality Prompt Restored) ---

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

    # THE HIGH QUALITY PROMPT
    prompt = f"""
    Role: Expert Resume Strategist.
    Task: Audit this resume for the role of "{target_role}".
    Resume Content: "{text[:3000]}"
    
    OUTPUT HTML ONLY. NO MARKDOWN.
    
    REQUIREMENTS:
    1. Summaries: Write 3 versions (Short/Medium/Long).
    2. Skills: Identify what the candidate HAS (Green) vs what is MISSING (Red) for "{target_role}".
    3. Bullets: Pick 3 weak bullet points and rewrite them to be result-oriented.
    
    USE THIS EXACT HTML STRUCTURE:

    <div class="analysis-container">
        <div class="mb-5 animate-fade-up">
            <h4 class="fw-bold text-dark mb-4"><i class="fas fa-pen-nib text-primary me-2"></i>Profile Summary Options</h4>
            <div class="row g-3">
                <div class="col-md-4">
                    <div class="p-4 border rounded-4 h-100 bg-white shadow-sm border-top-blue">
                        <h5 class="fw-bold text-primary mb-2">Short Version</h5>
                        <p class="text-dark small mb-0" style="line-height: 1.6;">{{Write Short Summary}}</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="p-4 border rounded-4 h-100 bg-white shadow-sm border-top-purple">
                        <h5 class="fw-bold text-purple mb-2">Medium Version</h5>
                        <p class="text-dark small mb-0" style="line-height: 1.6;">{{Write Medium Summary}}</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="p-4 border rounded-4 h-100 bg-white shadow-sm border-top-teal">
                        <h5 class="fw-bold text-teal mb-2">Long Version</h5>
                        <p class="text-dark small mb-0" style="line-height: 1.6;">{{Write Long Summary}}</p>
                    </div>
                </div>
            </div>
        </div>

        <div class="mb-5 animate-fade-up" style="animation-delay: 0.2s;">
            <h4 class="fw-bold text-dark mb-4"><i class="fas fa-chart-pie text-warning me-2"></i>Skill Gap Analysis</h4>
            <div class="row g-4">
                <div class="col-md-6">
                    <div class="p-4 rounded-4 h-100 bg-light-green border border-success">
                        <h6 class="fw-bold text-success mb-3"><i class="fas fa-check-circle me-2"></i>Skills You Have</h6>
                        <div class="d-flex flex-wrap gap-2">
                            {{Create 4-5 spans like this: <span class="badge bg-white text-success border border-success px-3 py-2 rounded-pill shadow-sm">Skill Name</span>}}
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="p-4 rounded-4 h-100 bg-light-red border border-danger">
                        <h6 class="fw-bold text-danger mb-3"><i class="fas fa-exclamation-triangle me-2"></i>Missing for {target_role}</h6>
                        <div class="d-flex flex-wrap gap-2">
                             {{Create 4-5 spans like this: <span class="badge bg-white text-danger border border-danger px-3 py-2 rounded-pill shadow-sm">Missing Skill</span>}}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="mb-4 animate-fade-up" style="animation-delay: 0.4s;">
            <h4 class="fw-bold text-dark mb-4"><i class="fas fa-magic text-purple me-2"></i>Bullet Point Improvements</h4>
            <div class="card border-0 shadow-sm rounded-4 overflow-hidden">
                <div class="table-responsive">
                    <table class="table table-bordered align-middle mb-0">
                        <thead class="bg-light">
                            <tr>
                                <th width="45%" class="text-muted text-uppercase small p-3">🔴 Weak Original</th>
                                <th width="10%" class="text-center bg-white border-0"></th>
                                <th width="45%" class="text-success text-uppercase small fw-bold p-3">🟢 Strong Rewrite</th>
                            </tr>
                        </thead>
                        <tbody>
                            {{Create 3 rows like this: 
                            <tr>
                                <td class="text-muted p-3 bg-light-red small">Weak Bullet</td>
                                <td class="text-center border-0"><i class="fas fa-arrow-right text-muted"></i></td>
                                <td class="fw-bold text-dark p-3 bg-light-green small">Strong Rewrite</td>
                            </tr>
                            }}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    """
    
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

# --- MODULE 2: INTERVIEW (High Quality Prompt Restored) ---

@app.route('/chatbot')
def interview_module():
    if 'user' not in session: return redirect('/')
    return render_template('interview.html')

@app.route('/interview/generate', methods=['POST'])
def generate_interview_questions():
    if 'user' not in session: return "Unauthorized", 401
    
    role = request.form.get('role')
    company = request.form.get('company')
    q_type = request.form.get('q_type')
    count = request.form.get('count')
    
    if 'resume' not in request.files: return "No file", 400
    file = request.files['resume']
    text = extract_text_from_pdf(file)

    prompt = f"""
    Act as a Senior Interviewer at {company}.
    Role: {role}.
    Candidate Resume: "{text[:2000]}"
    
    Task: Generate {count} {q_type} interview questions.
    FOR EACH QUESTION, PROVIDE A CONCISE "MODEL ANSWER".
    
    OUTPUT HTML ONLY. NO MARKDOWN.
    Use this exact card structure for EACH question:
    
    <div class="qa-card mb-4 animate-fade-up p-4 border rounded-4 shadow-sm bg-white">
        <div class="d-flex justify-content-between align-items-start mb-3">
            <h5 class="fw-bold text-dark w-100">Q: {{Question Text}}</h5>
        </div>
        <div class="d-flex align-items-center gap-2 mb-3">
            <button class="btn btn-sm btn-outline-danger rounded-pill fw-bold" onclick="toggleTimer(this)">
                <i class="fas fa-stopwatch me-1"></i> Timer
            </button>
            <span class="timer-display fw-bold text-danger me-3"></span>
            <button class="btn btn-sm btn-outline-success rounded-pill fw-bold" onclick="this.closest('.qa-card').querySelector('.answer-box').classList.toggle('d-none')">
                <i class="fas fa-eye me-1"></i> Show Answer
            </button>
        </div>
        <div class="p-3 bg-light rounded border small text-muted mb-2">
            <strong><i class="fas fa-lightbulb text-warning me-1"></i> Hint:</strong> {{One sentence hint}}
        </div>
        <div class="answer-box d-none p-3 bg-success bg-opacity-10 border border-success rounded text-dark small">
            <h6 class="fw-bold text-success mb-2"><i class="fas fa-check-circle me-2"></i>Model Answer</h6>
            {{Write a professional, concise model answer here}}
        </div>
    </div>
    """
    
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant"
        )
        return completion.choices[0].message.content.replace("```html", "").replace("```", "")
    except Exception as e:
        return f"<div class='alert alert-danger'>AI Error: {e}</div>"

@app.route('/interview/save', methods=['POST'])
def save_interview_result():
    if 'user' not in session: return "Unauthorized", 401
    
    data = request.json
    conn = get_db_connection()
    c = conn.cursor()
    
    content_str = data.get('content', '')
    role_str = f"Interview Prep: {data.get('role', 'General')}"
    
    if os.environ.get('DATABASE_URL'):
        c.execute("INSERT INTO reports (user_email, role, content, created_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP)", 
                 (session['user']['email'], role_str, content_str))
    else:
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        c.execute("INSERT INTO reports (user_email, role, content, created_at) VALUES (?, ?, ?, ?)", 
                 (session['user']['email'], role_str, content_str, now))
                 
    conn.commit()
    conn.close()
    return "Saved", 200

# --- MODULE 3: JOBS (Search & Save Restored) ---

@app.route('/jobs')
def job_search_module():
    if 'user' not in session: return redirect('/')
    return render_template('jobs.html')
@app.route('/jobs/search', methods=['POST'])
def search_jobs():
    if 'user' not in session: return "Unauthorized", 401
    
    role = request.form.get('role')
    location = request.form.get('location')
    
    # 1. API Call
    try:
        url = "https://api.adzuna.com/v1/api/jobs/in/search/1"
        params = {
            "app_id": os.getenv("ADZUNA_APP_ID"),
            "app_key": os.getenv("ADZUNA_APP_KEY"),
            "results_per_page": 10,
            "what": role,
            "where": location,
            "content-type": "application/json"
        }
        response = requests.get(url, params=params)
        data = response.json()
        
        jobs_data = []
        for job in data.get('results', []):
            jobs_data.append({
                "title": job.get('title'),
                "company": job.get('company', {}).get('display_name'),
                "location": job.get('location', {}).get('display_name'),
                "desc": job.get('description')[:140] + "...",
                "full_desc": job.get('description'), 
                "url": job.get('redirect_url'),
                "date": job.get('created')[:10] # Extracts YYYY-MM-DD
            })
            
    except Exception as e:
        return f"<div class='alert alert-danger'>API Error: {e}</div>"

    if not jobs_data:
        return "<div class='text-center mt-5'><h5 class='text-muted'>No jobs found. Check API Keys.</h5></div>"

    # 2. Generate Beautiful HTML
    html = ""
    for job in jobs_data:
        # Generate a cool avatar logo based on company name
        logo_url = f"https://ui-avatars.com/api/?name={job['company']}&background=random&size=128"
        
        safe_title = job['title'].replace("'", "").replace('"', "")
        
        html += f"""
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card h-100 border-0 shadow-sm rounded-4 hover-lift" style="transition: transform 0.2s;">
                <div class="card-body p-4 d-flex flex-column">
                    
                    <div class="d-flex align-items-center mb-3">
                        <img src="{logo_url}" class="rounded-circle me-3 border p-1" width="45" height="45" alt="Logo">
                        <div style="overflow: hidden;">
                            <h6 class="fw-bold text-dark mb-0 text-truncate">{job['title']}</h6>
                            <small class="text-primary fw-bold">{job['company']}</small>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <span class="badge bg-light text-dark border me-1">
                            <i class="fas fa-map-marker-alt me-1 text-danger"></i> {job['location']}
                        </span>
                        <span class="badge bg-light text-muted border">
                            <i class="far fa-clock me-1"></i> {job['date']}
                        </span>
                    </div>
                    
                    <p class="text-muted small mb-4 flex-grow-1" style="line-height: 1.6;">{job['desc']}</p>
                    
                    <div class="d-flex gap-2 mt-auto">
                        <a href="{job['url']}" target="_blank" class="btn btn-dark rounded-pill fw-bold btn-sm flex-grow-1">
                            Apply Now <i class="fas fa-external-link-alt ms-1"></i>
                        </a>
                        <button onclick="saveJob(this, '{safe_title}', '{job['company']}', '{job['location']}', '{job['url']}')" 
                                class="btn btn-outline-secondary rounded-pill btn-sm" title="Save Job">
                            <i class="far fa-bookmark"></i>
                        </button>
                    </div>

                </div>
            </div>
        </div>
        """
    return html


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

# --- MODULE 4: COURSES (Golden Ticket Prompt Restored) ---

@app.route('/courses')
def course_module():
    if 'user' not in session: return redirect('/')
    return render_template('courses.html')

@app.route('/courses/gap_analysis', methods=['POST'])
def gap_analysis_courses():
    if 'user' not in session: return "Unauthorized", 401
    
    role = request.form.get('role')
    file = request.files['resume']
    resume_text = extract_text_from_pdf(file)
    
    if len(resume_text) < 50: return "<div class='text-white text-center'>Resume unreadable.</div>"

    prompt = f"""
    Role: Senior Career Architect.
    Task: Create a "Skill Bridge" roadmap for a candidate aiming for "{role}".
    
    1. Identify 3 CRITICAL MISSING SKILLS.
    2. For each, recommend ONE top-tier FREE COURSE.
    
    OUTPUT HTML CARDS ONLY. Use this "Golden Ticket" structure:
    
    <div class="col-lg-4 col-md-6 fade-in">
        <div class="card h-100 course-card border-0 shadow-lg position-relative overflow-hidden" style="border-radius: 20px;">
            <div class="card-body p-4 d-flex flex-column">
                <div class="d-flex align-items-center mb-3">
                    <div class="icon-square bg-warning bg-opacity-10 text-warning rounded-3 p-3 me-3">
                        <i class="fas fa-exclamation-triangle fa-lg"></i>
                    </div>
                    <div>
                        <small class="text-muted fw-bold text-uppercase ls-1" style="font-size: 0.7rem;">MISSING SKILL</small>
                        <h5 class="fw-bold text-dark mb-0">{{Skill Name}}</h5>
                    </div>
                </div>
                
                <div class="my-3 border-top border-bottom py-3">
                    <small class="text-primary fw-bold text-uppercase mb-1 d-block">Recommended Fix</small>
                    <h6 class="fw-bold text-dark mb-1">{{Course Name}}</h6>
                    <div class="d-flex align-items-center text-muted small">
                        <i class="fas fa-university me-2 text-secondary"></i>
                        <span>{{Provider Name}}</span>
                    </div>
                </div>
                
                <a href="{{Course Link}}" target="_blank" class="btn btn-primary bg-gradient w-100 py-3 rounded-pill fw-bold shadow-sm mt-auto hover-scale text-uppercase">
                    Claim Free Certificate <i class="fas fa-external-link-alt ms-2"></i>
                </a>
            </div>
        </div>
    </div>
    """
    
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.3
        )
        return completion.choices[0].message.content.replace("```html", "").replace("```", "")
    except Exception as e:
        return f"<div class='alert alert-danger'>AI Error: {e}</div>"

# --- ADMIN & UTILS ---

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
        total_scans = res['count'] if res else 0
    else:
        c.execute("SELECT * FROM users ORDER BY last_login DESC")
        users = c.fetchall()
        c.execute("SELECT COUNT(*) FROM reports")
        total_scans = c.fetchone()[0]
    
    conn.close()
    return render_template('admin.html', users=users, total_users=len(users), total_scans=total_scans)

# --- EMERGENCY DB RESET ROUTE (Fixes All "Missing Column" Errors) ---
@app.route('/nuclear-reset')
def nuclear_reset():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. DELETE ALL OLD TABLES (Force Clean Slate)
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