# Online Judge

An online judge system built with FastAPI, Jinja2, SQLite, Bootstrap 5, and Bubblewrap for sandboxed code execution.

## Features

* User authentication (registration, login, logout)
* View contests and problems loaded from the filesystem
* Submit code solutions (Python, C, C++)
* Sandboxed execution of user code using Bubblewrap and resource limits
* Asynchronous submission processing
* View submission results (status, time, memory, output/errors)
* Database for users and submissions (SQLite)
* Responsive UI

## Getting Started

### Prerequisites

* Python (v3.13 recommended)
* `bubblewrap` (`bwrap`) installed on your system.
* `gcc` and `g++` installed (for C and C++ support).

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/CrapTheCoder/Dockerless-Online-Judge
   cd <repository_directory>
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   Create a `.env` file in the project root directory with necessary configurations.
   ```env
   SECRET_KEY=your_strong_random_jwt_secret_key
   SESSION_SECRET_KEY=your_strong_random_session_secret_key
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   DATABASE_URL=sqlite:///./judge.db
   # Optional: If g++ is not in your default PATH, you can specify it
   # GPP_PATH=/path/to/your/g++
   ```

5. **Set up the Database:**
   This project uses SQLAlchemy and Alembic for database migrations.
   ```bash
   # Initialize Alembic (only if you haven't run this command before)
   alembic init alembic 

   # Generate migration based on models (if models changed since last migration)
   alembic revision --autogenerate -m "add user and submission tables"
   
   alembic upgrade head
   ```

6. **Prepare Contest Data:**
   Place your contest and problem definition files (markdown, json, input/output) in the `server_data/contests/`
   directory. The application will load these on startup.

### Running the Application

**Note:** The current sandboxing implementation using `bwrap` and `resource` limits requires superuser privileges. We
use `su` for ease of development. **This is very UNSAFE for production, and will be fixed in the future.**

Make sure you are in the project root and your virtual environment is active.

```bash
su
fastapi dev app/main.py
```

Once the server is running, open your browser to:

* **Web UI:** `http://127.0.0.1:8000/`
* **API Docs:** `http://127.0.0.1:8000/docs`
