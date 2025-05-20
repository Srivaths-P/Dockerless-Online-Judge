# Dockerless Online Judge (DOJ)

An online judge system built with FastAPI, Jinja2, SQLite, Nginx, and a robust sandboxing mechanism using `systemd-run` scopes and `bubblewrap`.

## Features

*   User authentication (registration, login, logout via UI cookies and API tokens).
*   View contests and problems loaded from the filesystem (Markdown descriptions, JSON settings).
*   Python, C, C++ support for submissions.
*   Secure sandboxed execution of user code using `systemd-run --user` scopes and `bubblewrap` for resource limiting (CPU time, memory, tasks) and filesystem isolation.
*   Asynchronous submission processing via an `asyncio` queue and worker pool.
*   View submission results (status, execution time, memory usage, stdout/stderr).
*   Test case generator: Users can request sample input/output for problems with defined generator scripts, executed in a sandbox.
*   Database for users (with rate limit tracking) and submissions (SQLite with Alembic for migrations). WAL enabled for SQLite for improved concurrency.
*   Comprehensive JSON-based logging of user activity and submission lifecycle events for analytics.
*   Responsive UI built with Bootstrap 5 and Jinja2 templates.
*   RESTful API for core functionalities.

## Getting Started (Development)

### Prerequisites

*   Linux operating system (for `systemd` and `bubblewrap`).
*   Python (v3.11+ recommended).
*   `bubblewrap` (`bwrap`) installed system-wide.
*   `gcc` and `g++` installed (for C and C++ support).
*   `systemd` (usually present on modern Linux distributions).
*   The user running the application needs user lingering enabled for `systemd --user` scopes to work reliably if the app is daemonized.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/CrapTheCoder/Dockerless-Online-Judge.git
    cd Dockerless-Online-Judge
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    Create a `.env` file in the project root directory:
    ```env
    SECRET_KEY=your_jwt_secret_key
    SESSION_SECRET_KEY=your_random_session_secret_key
    ALGORITHM=HS256
    ACCESS_TOKEN_EXPIRE_MINUTES=30
    DATABASE_URL=sqlite:///./judge.db
    ```

5.  **Set up the Database:**
    This project uses SQLAlchemy and Alembic for database migrations.
    ```bash
    source .venv/bin/activate
    alembic upgrade head
    ```

6.  **Prepare Contest Data:**
    Place your contest and problem definition files (markdown, json for settings including timing and generator limits, `generator.py` scripts, input/output files) in the `server_data/contests/` directory. The application loads these on startup.

### Running the Application (Development)

Ensure you have `bubblewrap` installed and you can run `systemd --user` services.

Make sure you are in the project root and your virtual environment is active:
```bash
source .venv/bin/activate
fastapi dev app/main.py
```

---

## Future Work

*   Code Execution:
    *   Support for more programming languages.
    *   Support for interactive problems.
    *   Custom checkers for problems with many correct outputs.
*   Backend:
    *   Consider PostgreSQL for production deployments.
    *   Implement database backups.
    *   Implement an admin API.
*   User Interface:
    *   Real-time submission status updates (e.g., using WebSockets or Server-Sent Events) instead of page reloads.
    *   Allow users to view submissions of other participants after a contest ends.
    *   Contest leaderboards.
*   Testing:
    *   More comprehensive unit and integration tests.
    *   End-to-end tests for UI and API workflows.
