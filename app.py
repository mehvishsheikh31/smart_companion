import os
import sqlite3
import datetime
import requests # <--- THIS WAS MISSING
import json     # <--- THIS WAS MISSING
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
# --- ADD THIS HELPER FUNCTION AT THE TOP OF APP.PY ---
import pdfplumber

def extract_text_from_pdf(file):
    try:
        with pdfplumber.open(file) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            return text
    except Exception as e:
        return ""
# Database Setup
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 1. Create Users Table with ALL columns (New & Old)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY, 
            name TEXT, 
            picture TEXT,
            last_login TEXT,
            login_count INTEGER DEFAULT 0
        )
    ''')

    # 2. Create Reports Table
    c.execute('''CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, role TEXT, content TEXT, created_at TEXT)''')
    
    # 3. Create Jobs Table
    c.execute('''CREATE TABLE IF NOT EXISTS saved_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, title TEXT, company TEXT, location TEXT, url TEXT, created_at TEXT)''')
    
    # 4. Create Cache Table
    c.execute('''CREATE TABLE IF NOT EXISTS job_cache (search_key TEXT PRIMARY KEY, json_data TEXT, updated_at TEXT)''')
    
    conn.commit()
    conn.close()

# Run it immediately
init_db()

def extract_text_from_pdf(pdf_file):
    try:
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            extract = page.extract_text()
            if extract: text += extract + "\n"
        return text
    except:
        return ""

# --- CORE ROUTES ---
@app.route('/')
def home():
    if 'user' in session:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row # Allows accessing columns by name
        c = conn.cursor()
        
        # 1. Fetch Recent Resume Reports
        c.execute("SELECT * FROM reports WHERE user_email = ? ORDER BY id DESC LIMIT 3", (session['user']['email'],))
        saved_reports = c.fetchall()
        
        # 2. Fetch Saved Jobs (NEW)
        c.execute("SELECT * FROM saved_jobs WHERE user_email = ? ORDER BY id DESC LIMIT 5", (session['user']['email'],))
        saved_jobs_list = c.fetchall()
        
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
    user_info = google.userinfo()
    session['user'] = user_info
    
    # --- TRACK USER LOGIN ---
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Try to Insert New User
    c.execute("INSERT OR IGNORE INTO users (email, name, picture, login_count) VALUES (?, ?, ?, 0)", 
              (user_info['email'], user_info['name'], user_info['picture']))
    
    # 2. Update Login Stats (Increment count, set time)
    c.execute("UPDATE users SET last_login = ?, login_count = login_count + 1 WHERE email = ?", 
              (now, user_info['email']))
              
    conn.commit()
    conn.close()
    
    return redirect('/')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# --- MODULE 1: RESUME ---
@app.route('/resume')
def resume_module():
    if 'user' not in session: return redirect('/')
    return render_template('resume.html')
# --- MODULE 1: DEEP RESUME SURGERY (Actionable Value, No Score) ---
# --- MODULE 1: CUSTOM RESUME STRATEGY (Short/Med/Long + Gaps) ---
# --- MODULE 1: COMPLETE RESUME STRATEGY (Summaries + Skills + Rewrites) ---
@app.route('/resume/analyze', methods=['POST'])
def analyze_resume():
    if 'user' not in session: return redirect('/')
    
    if 'resume' not in request.files: return "No file uploaded", 400
    file = request.files['resume']
    target_role = request.form.get('job_role')
    
    text = extract_text_from_pdf(file)
    if len(text) < 50: return "Resume is too short or unreadable.", 400

    # PROMPT: The "All-In-One" Strategy
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
                        <small class="text-muted d-block mb-3">Perfect for "About Me" or Elevator Pitch</small>
                        <p class="text-dark small mb-0" style="line-height: 1.6;">{{Write Short Summary}}</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="p-4 border rounded-4 h-100 bg-white shadow-sm border-top-purple">
                        <h5 class="fw-bold text-purple mb-2">Medium Version</h5>
                        <small class="text-muted d-block mb-3">Standard LinkedIn/Resume Summary</small>
                        <p class="text-dark small mb-0" style="line-height: 1.6;">{{Write Medium Summary}}</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="p-4 border rounded-4 h-100 bg-white shadow-sm border-top-teal">
                        <h5 class="fw-bold text-teal mb-2">Long Version</h5>
                        <small class="text-muted d-block mb-3">Detailed Bio or Cover Letter Opener</small>
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
                            <span class="badge bg-white text-success border border-success px-3 py-2 rounded-pill shadow-sm">{{Skill Found 1}}</span>
                            <span class="badge bg-white text-success border border-success px-3 py-2 rounded-pill shadow-sm">{{Skill Found 2}}</span>
                            <span class="badge bg-white text-success border border-success px-3 py-2 rounded-pill shadow-sm">{{Skill Found 3}}</span>
                            <span class="badge bg-white text-success border border-success px-3 py-2 rounded-pill shadow-sm">{{Skill Found 4}}</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="p-4 rounded-4 h-100 bg-light-red border border-danger">
                        <h6 class="fw-bold text-danger mb-3"><i class="fas fa-exclamation-triangle me-2"></i>Missing for {{target_role}}</h6>
                        <div class="d-flex flex-wrap gap-2">
                            <span class="badge bg-white text-danger border border-danger px-3 py-2 rounded-pill shadow-sm">{{Missing Skill 1}}</span>
                            <span class="badge bg-white text-danger border border-danger px-3 py-2 rounded-pill shadow-sm">{{Missing Skill 2}}</span>
                            <span class="badge bg-white text-danger border border-danger px-3 py-2 rounded-pill shadow-sm">{{Missing Skill 3}}</span>
                            <span class="badge bg-white text-danger border border-danger px-3 py-2 rounded-pill shadow-sm">{{Missing Skill 4}}</span>
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
                            <tr>
                                <td class="text-muted p-3 bg-light-red small">{{Quote Weak Bullet 1}}</td>
                                <td class="text-center border-0"><i class="fas fa-arrow-right text-muted"></i></td>
                                <td class="fw-bold text-dark p-3 bg-light-green small">{{Rewrite Strong Bullet 1}}</td>
                            </tr>
                            <tr>
                                <td class="text-muted p-3 bg-light-red small">{{Quote Weak Bullet 2}}</td>
                                <td class="text-center border-0"><i class="fas fa-arrow-right text-muted"></i></td>
                                <td class="fw-bold text-dark p-3 bg-light-green small">{{Rewrite Strong Bullet 2}}</td>
                            </tr>
                            <tr>
                                <td class="text-muted p-3 bg-light-red small">{{Quote Weak Bullet 3}}</td>
                                <td class="text-center border-0"><i class="fas fa-arrow-right text-muted"></i></td>
                                <td class="fw-bold text-dark p-3 bg-light-green small">{{Rewrite Strong Bullet 3}}</td>
                            </tr>
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
        content = completion.choices[0].message.content
        
        # Cleanup
        content = content.replace("```html", "").replace("```", "")
        
        # Save to DB
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
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
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    report = c.fetchone()
    conn.close()
    
    if report:
        return render_template('resume_result.html', analysis=report['content'])
    else:
        return "Report not found", 404
# --- MODULE 2: INTERVIEW ---
@app.route('/chatbot')
def interview_module():
    if 'user' not in session: return redirect('/')
    return render_template('interview.html')

# --- ROUTE 1: GENERATE QUESTIONS (WITH ANSWERS) ---
@app.route('/interview/generate', methods=['POST'])
def generate_interview_questions():
    if 'user' not in session: return "Unauthorized", 401
    
    # 1. Get Data
    role = request.form.get('role')
    company = request.form.get('company')
    q_type = request.form.get('q_type')
    count = request.form.get('count')
    
    # 2. Extract Resume Text
    if 'resume' not in request.files: return "No file", 400
    file = request.files['resume']
    text = extract_text_from_pdf(file)

    # 3. AI Prompt (Updated to ask for Answers)
    prompt = f"""
    Act as a Senior Interviewer at {company}.
    Role: {role}.
    Candidate Resume: "{text[:2000]}"
    
    Task: Generate {count} {q_type} interview questions tailored to this resume. 
    FOR EACH QUESTION, PROVIDE A CONCISE "MODEL ANSWER".
    
    OUTPUT HTML ONLY. NO MARKDOWN.
    Use this exact card structure for EACH question:
    
    <div class="qa-card mb-4 animate-fade-up p-4 border rounded-4 shadow-sm bg-white">
        
        <div class="d-flex justify-content-between align-items-start mb-3">
            <h5 class="fw-bold text-dark w-100">Q: {{Question Text}}</h5>
            <span class="badge bg-primary bg-opacity-10 text-primary border border-primary">{{Difficulty Level}}</span>
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

# --- ROUTE 2: IMPROVE ANSWER ---
@app.route('/interview/improve', methods=['POST'])
def improve_answer():
    if 'user' not in session: return "Unauthorized", 401
    
    data = request.json
    question = data.get('question')
    answer = data.get('answer')
    
    prompt = f"""
    Act as an Interview Coach.
    Question: "{question}"
    Candidate Answer: "{answer}"
    
    Task: Critique and Rewrite.
    
    OUTPUT HTML ONLY:
    <div class="p-3 bg-white border rounded-3 mt-3 shadow-sm">
        <h6 class="text-danger fw-bold mb-2"><i class="fas fa-times-circle me-2"></i>Critique</h6>
        <p class="small text-muted">{{2 sentences on what was wrong}}</p>
        
        <h6 class="text-success fw-bold mb-2 mt-3"><i class="fas fa-check-circle me-2"></i>Better Version</h6>
        <p class="small text-dark fw-bold" style="background:#f0fff4; padding:10px; border-radius:10px;">{{Write the perfect answer}}</p>
    </div>
    """
    
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant"
        )
        return completion.choices[0].message.content.replace("```html", "").replace("```", "")
    except Exception as e:
        return f"Error: {e}"

# --- ROUTE 3: SAVE RESULT ---
@app.route('/interview/save', methods=['POST'])
def save_interview_result():
    if 'user' not in session: return "Unauthorized", 401
    
    data = request.json
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Save as a "Report" but with type 'Interview'
    c.execute("INSERT INTO reports (user_email, role, content, created_at) VALUES (?, ?, ?, ?)", 
              (session['user']['email'], f"Interview Prep: {data['role']}", data['content'], now))
    conn.commit()
    conn.close()
    return "Saved", 200
# --- MODULE 3: REAL-TIME JOB SEARCH (INDIA) ---

@app.route('/jobs')
def job_search_module():
    if 'user' not in session: return redirect('/')
    return render_template('jobs.html')

@app.route('/jobs/search', methods=['POST'])
def search_jobs():
    if 'user' not in session: return "Unauthorized", 401
    
    role = request.form.get('role')
    location = request.form.get('location')
    
    # 1. Check Database Cache
    search_key = f"{role}_{location}_in".lower()
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Ensure table exists
    c.execute('''CREATE TABLE IF NOT EXISTS job_cache (search_key TEXT PRIMARY KEY, json_data TEXT, updated_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS saved_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, title TEXT, company TEXT, location TEXT, url TEXT, created_at TEXT)''')
    c.execute("SELECT json_data, updated_at FROM job_cache WHERE search_key = ?", (search_key,))
    cached = c.fetchone()
    
    jobs_data = []
    
    # Use Cache if < 24 hours old
    if cached and (datetime.datetime.now() - datetime.datetime.strptime(cached[1], "%Y-%m-%d %H:%M:%S") < datetime.timedelta(hours=24)):
        jobs_data = json.loads(cached[0])
    else:
        # 2. Call Adzuna API
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
            
            for job in data.get('results', []):
                jobs_data.append({
                    "title": job.get('title'),
                    "company": job.get('company', {}).get('display_name'),
                    "location": job.get('location', {}).get('display_name'),
                    "desc": job.get('description')[:140] + "...",
                    "full_desc": job.get('description'), 
                    "url": job.get('redirect_url'),
                    "date": job.get('created')[:10]
                })

            if jobs_data:
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("INSERT OR REPLACE INTO job_cache (search_key, json_data, updated_at) VALUES (?, ?, ?)", 
                          (search_key, json.dumps(jobs_data), now_str))
                conn.commit()

        except Exception as e:
            return f"<div class='alert alert-danger'>API Error: {e}</div>"
    
    conn.close()

    # 3. Generate Beautiful HTML Cards
    if not jobs_data:
        return "<div class='text-center mt-5'><h5 class='text-muted'>No active jobs found in this city. Try 'Bangalore' or 'Remote'.</h5></div>"

    html = ""
    for job in jobs_data:
        logo_url = f"https://ui-avatars.com/api/?name={job['company']}&background=random&size=128"
        
        # Clean text for JavaScript
        safe_title = job['title'].replace("'", "").replace('"', "")
        safe_desc = job['full_desc'].replace("'", "").replace('"', "").replace("\n", " ")

       
        html += f"""
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card h-100 border-0 shadow-sm rounded-4 job-card hover-lift">
                <div class="card-body p-4 d-flex flex-column">
                    <div class="d-flex align-items-center mb-3">
                        <img src="{logo_url}" class="rounded-circle me-3 border p-1" width="45" height="45">
                        <div>
                            <h6 class="fw-bold text-dark mb-0">{job['title']}</h6>
                            <small class="text-primary fw-bold">{job['company']}</small>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <span class="badge bg-light text-dark border me-1"><i class="fas fa-map-marker-alt me-1 text-danger"></i> {job['location']}</span>
                        <span class="badge bg-light text-muted border"><i class="far fa-clock me-1"></i> {job['date']}</span>
                    </div>
                    
                    <p class="text-muted small mb-4 flex-grow-1">{job['desc']}</p>
                    
                    <div class="d-grid gap-2 mt-auto">
                        <div class="d-flex gap-2">
                            <a href="{job['url']}" target="_blank" class="btn btn-outline-dark rounded-pill fw-bold btn-sm flex-grow-1">
                                Apply <i class="fas fa-external-link-alt ms-1"></i>
                            </a>
                            <button onclick="saveJob(this, '{safe_title}', '{job['company']}', '{job['location']}', '{job['url']}')" class="btn btn-outline-secondary rounded-pill btn-sm" title="Save Job">
                                <i class="far fa-bookmark"></i>
                            </button>
                        </div>
                        <button onclick="analyzeMatch('{safe_title}', '{safe_desc}')" class="btn btn-primary bg-gradient border-0 rounded-pill fw-bold btn-sm shadow-sm">
                            <i class="fas fa-magic me-2"></i> Check Match %
                        </button>
                    </div>
                </div>
            </div>
        </div>
        """
    return html

# --- UPDATE THIS FUNCTION IN app.py ---

@app.route('/jobs/analyze_match', methods=['POST'])
def analyze_job_match():
    if 'user' not in session: return "Unauthorized", 401
    
    if 'resume' not in request.files: return "<div class='text-danger'>Please upload a resume first!</div>"
    file = request.files['resume']
    job_title = request.form.get('job_title')
    job_desc = request.form.get('job_desc')
    
    resume_text = extract_text_from_pdf(file)
    if not resume_text: return "<div class='text-danger'>Resume unreadable.</div>"
    
    # PROMPT: Generate an Infographic Structure
    prompt = f"""
    Act as a Visual Career Coach.
    Resume: "{resume_text[:2000]}"
    Target Job: "{job_title}"
    Job Desc: "{job_desc[:1000]}"
    
    TASK: Output HTML ONLY for a visual scorecard.
    
    STRUCTURE:
    <div class="score-container text-center">
        <div class="score-circle mb-3 mx-auto" style="border-color: {{color}};">
            <span class="score-number" style="color: {{color}};">{{Score}}%</span>
            <span class="score-label">MATCH</span>
        </div>
        
        <h4 class="fw-bold mb-4" style="color: {{color}};">{{One Word Verdict: e.g. Perfect Fit / Good Match / Low Match}}</h4>
        
        <div class="row g-3 text-start">
            <div class="col-md-6">
                <div class="p-3 rounded-4 h-100" style="background: #e8f5e9;">
                    <h6 class="text-success fw-bold mb-2"><i class="fas fa-check-circle me-2"></i>Why you fit</h6>
                    <ul class="mb-0 small text-dark ps-3">
                        <li>{{Strength 1}}</li>
                        <li>{{Strength 2}}</li>
                    </ul>
                </div>
            </div>
            <div class="col-md-6">
                <div class="p-3 rounded-4 h-100" style="background: #fff3e0;">
                    <h6 class="text-warning fw-bold mb-2"><i class="fas fa-exclamation-triangle me-2"></i>Missing Skills</h6>
                    <ul class="mb-0 small text-dark ps-3">
                        <li>{{Gap 1}}</li>
                        <li>{{Gap 2}}</li>
                    </ul>
                </div>
            </div>
        </div>
        
        <div class="mt-4 p-2 bg-light rounded-3 border">
            <small class="text-muted fw-bold">💡 RECOMMENDATION: {{One short sentence advice}}</small>
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
# --- ADD THIS NEW ROUTE FOR SAVING JOBS ---
@app.route('/jobs/save', methods=['POST'])
def save_job():
    if 'user' not in session: return "Unauthorized", 401
    
    data = request.json
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Check if already saved
    c.execute("SELECT id FROM saved_jobs WHERE user_email = ? AND url = ?", (session['user']['email'], data['url']))
    if c.fetchone():
        conn.close()
        return "Already saved", 200
        
    # Insert new job
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO saved_jobs (user_email, title, company, location, url, created_at) VALUES (?, ?, ?, ?, ?, ?)", 
              (session['user']['email'], data['title'], data['company'], data['location'], data['url'], now))
    conn.commit()
    conn.close()
    return "Saved", 200
# (Keep your analyze_match route here)

# --- MODULE 4: INTELLIGENT GAP ANALYSIS & COURSE RECOMMENDER ---

# --- MODULE 4: INTELLIGENT GAP ANALYSIS & COURSE RECOMMENDER ---

@app.route('/courses')
def course_module():
    if 'user' not in session: return redirect('/')
    return render_template('courses.html')

@app.route('/courses/gap_analysis', methods=['POST'])
def gap_analysis_courses():
    if 'user' not in session: return "Unauthorized", 401
    
    # 1. Get Inputs
    role = request.form.get('role')
    file = request.files['resume']
    resume_text = extract_text_from_pdf(file)
    
    if len(resume_text) < 50: return "<div class='text-white text-center'>Resume unreadable.</div>"

    # 2. AI Prompt (Visual "Golden Ticket" Style)
    prompt = f"""
    Role: Senior Career Architect.
    Task: Create a "Skill Bridge" roadmap for a candidate aiming for "{role}".
    
    1. Identify 3 CRITICAL MISSING SKILLS.
    2. For each, recommend ONE top-tier FREE COURSE (Cisco, freeCodeCamp, Kaggle, IBM, Google).
    
    OUTPUT HTML CARDS ONLY. Use this "Golden Ticket" structure:
    
    <div class="col-lg-4 col-md-6 fade-in">
        <div class="card h-100 course-card border-0 shadow-lg position-relative overflow-hidden" style="border-radius: 20px;">
            <div class="position-absolute top-0 end-0 bg-primary opacity-10 rounded-circle" style="width: 150px; height: 150px; transform: translate(30%, -30%);"></div>
            
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

                <div class="d-flex gap-2 mb-4">
                    <span class="badge bg-success bg-opacity-10 text-success border border-success rounded-pill px-3">
                        <i class="fas fa-tag me-1"></i> FREE
                    </span>
                    <span class="badge bg-light text-dark border rounded-pill px-3">
                        <i class="fas fa-certificate me-1"></i> Certificate
                    </span>
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
    
 # ==========================================
# MODULE 5: ADMIN DASHBOARD (ANALYTICS)
# ==========================================
@app.route('/admin')
def admin_panel():
    if 'user' not in session: return redirect('/')
    
    # SECURITY CHECK: Only YOU can see this page
    # Replace this with your EXACT Google Email
    admin_email = 'mehvishsheikh.3101@gmail.com' 
    
    if session['user']['email'] != admin_email: 
        return f"<h1 style='color:red; text-align:center; margin-top:50px;'>403 Forbidden<br>You are not the Admin.</h1>", 403

    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row # This allows us to access columns by name
    c = conn.cursor()
    
    # 1. Get List of All Users
    c.execute("SELECT * FROM users ORDER BY last_login DESC")
    users = c.fetchall()
    
    # 2. Get Total Usage Stats
    total_users = len(users)
    
    # 3. Calculate Total Scans (Optional: just counting rows in reports)
    c.execute("SELECT COUNT(*) FROM reports")
    total_scans = c.fetchone()[0]
    
    conn.close()
    
    return render_template('admin.html', users=users, total_users=total_users, total_scans=total_scans)
if __name__ == '__main__':
    app.run(debug=True)