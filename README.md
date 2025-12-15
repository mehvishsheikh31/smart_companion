# 🚀 Smart Companion  
### AI-Powered Career Preparation Platform

**Smart Companion** is a full-stack web application that helps job seekers optimize resumes, practice interviews, search for relevant jobs, and close skill gaps using AI-driven insights.  
The platform focuses on **speed, realism, and personalization**, delivering low-latency AI responses through modern inference infrastructure.

🔗 **Live Application:**  
https://smart-companion.onrender.com/

🔗 **GitHub Repository:**  
https://github.com/mehvishsheikh31/smart_companion/

---
<img width="1549" height="869" alt="Screenshot 2025-12-15 183300" src="https://github.com/user-attachments/assets/780747c0-9065-4e81-b4ad-78199b3252c9" />

## 📌 What Problem It Solves
- Poorly optimized resumes rejected by ATS systems
- Lack of realistic interview practice
- Difficulty finding relevant job openings
- Unclear learning paths for required skills

Smart Companion addresses the **entire job-seeking lifecycle** in one platform.

---

## 💡 Core Modules

| Module | Purpose | Description |
|------|--------|-------------|
| **Resume Deep Scan** | Resume Optimization | Upload a PDF resume and target a job role. Generates **Concise, Medium, and Detailed summaries**, keyword optimization, and quantified improvement suggestions. |
| **Interview Mastery Hub** | Interview Practice | AI-based HR interviewer chatbot with contextual memory and follow-up questions. Includes **Answer Refiner** for critique and professional rewrites. |
| **Real-Time Job Search** | Job Discovery | Fetches live job listings based on role, experience, and location using external APIs. |
| **Course Recommender** | Skill Gap Analysis | Analyzes missing skills and recommends relevant online courses and certifications. |

🔐 All modules are accessible **only after secure user authentication**.
<img width="1758" height="813" alt="Screenshot 2025-12-15 183334" src="https://github.com/user-attachments/assets/7343a309-53eb-4983-865d-f3254ee83c05" />



## ⚙️ Full Technology Stack

### 🖥️ Frontend
| Technology | Usage |
|----------|------|
| **HTML5** | Page structure |
| **CSS3** | Custom styling and layouts |
| **Bootstrap 5** | Responsive UI components |
| **JavaScript (ES6)** | Client-side interactivity |
| **Jinja2** | Server-side template rendering |

---

### 🧠 Backend
| Technology | Usage |
|----------|------|
| **Python 3** | Core backend language |
| **Flask** | Routing, APIs, and session handling |
| **Gunicorn** | Production WSGI server |

---

| Technology              | Usage                                                                                                                 |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **PostgreSQL (Render)** | Production database storing user profiles, authentication data, login history, and analytics information in the cloud |
| **SQLite (Local)**      | Lightweight development database used for local testing and rapid setup without external dependencies                 |
| **Psycopg2**            | Python adapter for establishing secure connections between Flask backend and PostgreSQL database                      |
| **Server-Side Storage** | Temporary storage for uploaded resume PDFs during processing and text extraction                                      |


### 🔐 Authentication & Security
| Feature | Implementation |
|-------|---------------|
| User Registration & Login | Flask-based authentication |
| Password Storage | Hashed passwords (Werkzeug Security) |
| Session Management | Session-based authentication |
| Route Protection | Restricted access to dashboards and AI modules |
| Logout | Secure session termination |

---

### 🗄️ Database & Storage
| Technology | Usage |
|----------|------|
| **SQLite** | User data, login history, generated reports |
| **SQL Queries / Flask ORM** | Database operations |
| **Server-Side File Storage** | Resume PDF uploads |

---

### 📄 Resume Processing
| Technology | Usage |
|----------|------|
| **pdfplumber** | Extract text from resume PDFs |
| **Python NLP Logic** | Skill extraction and keyword analysis |

---

### 🤖 AI & Intelligence Layer
| Technology | Usage |
|----------|------|
| **Groq API** | Ultra-low latency AI inference |
| **Llama 3.1 (8B)** | Resume analysis, interview simulation |
| **Prompt Engineering** | Context-aware responses |
| **Conversation Memory** | Maintains interview flow |

⚠️ Note: No fine-tuning is claimed — models are used via inference APIs.

---

### 🌐 External Integrations
| Service | Usage |
|--------|------|
| **Job Search APIs / Web Requests** | Fetch live job openings |
| **Course Platforms** | Course recommendations |

-


## 🧪 Development Tools
- VS Code / PyCharm
- Flask Debug Mode
- Browser Developer Tools
- Postman (API testing)

---

## 🧠 Key Highlights
- ⚡ Ultra-fast AI responses using Groq
- 🔐 Secure, session-based authentication
- 📄 ATS-friendly resume optimization
- 🎤 Realistic interview simulation
- 🌐 Fully deployed production app

---

## 📊 Project Status
- ✅ Fully implemented
- ✅ Deployed and live
- ✅ Secure authentication
- ✅ Suitable for portfolio, academic submission, and interviews

---

## 👤 Author
**Mehvish Sheikh**  
B.Tech – Data Science  

🔗 GitHub: https://github.com/mehvishsheikh31  
🔗 Live App: https://smart-companion.onrender.com/

---

## 🚀 Future Enhancements
- OAuth (GitHub login)
- Resume version comparison
- Analytics dashboard
- Multi-language support

---

⭐ If you find this project useful, consider giving it a star!