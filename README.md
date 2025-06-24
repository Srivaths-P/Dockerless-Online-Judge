# [Dockerless Online Judge](https://doj.sriv.in/) (DOJ)

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Framework](https://img.shields.io/badge/Framework-FastAPI-green.svg)](https://fastapi.tiangolo.com/)

A secure, high-performance, self-hosted online judge built with FastAPI. It leverages a robust, multi-layered sandboxing mechanism using `systemd` scopes and `bubblewrap` for resource control and isolation, eliminating the need for Docker or other containerization overhead.

## Overview

The Dockerless Online Judge (DOJ) provides a complete platform for hosting competitive programming contests. It features a clean web interface for users and a RESTful API for programmatic access. The core of the system is its unique sandboxing architecture, which uses low-level Linux features to securely compile and execute untrusted user code with precise resource measurement and control.

Contests and problems are defined through a simple filesystem structure, making content management straightforward and version-controllable.

## Core Features

*   **User Authentication:** Secure single sign-on with Google. User sessions are handled via cookies and persist until the browser is closed.
*   **Filesystem-based Content:** Contests and problems are loaded directly from a structured directory. Includes a secure admin endpoint for hot-reloading data without server restarts.
*   **Multi-language Support:** Support for `C++`, `C`, and `Python`. The architecture is easily extendable to other languages.
*   **Secure Sandboxed Execution:** A multi-layered security model to safely run untrusted code:
    *   **Accurate CPU Time Limiting (`setrlimit`):** The sandbox uses the kernel's `setrlimit` call to enforce a strict **CPU time limit**. This is the standard for competitive programming judges, as it is unaffected by system load.
    *   **Resource Enforcement (`systemd`):** A `systemd` scope provides a secondary wall-clock safety net and enforces hard limits on memory usage (MLE) and process count (preventing fork bombs) using kernel cgroups.
    *   **Filesystem & Network Isolation (`bubblewrap`):** User code is executed in a tightly sealed container with no network access and a read-only view of essential system libraries.
*   **Asynchronous Judging:** Submissions are pushed to a high-performance `asyncio` queue and processed by a pool of background workers, ensuring the web interface remains fast and responsive.
*   **Advanced Judging Logic:**
    *   **Custom Validators:** Support for problems with multiple correct answers via custom validator scripts.
    *   **Test Case Generators:** Problems can include a `generator` script that users can trigger from the UI to see sample test cases.
*   **Contest Lifecycle Management:** Full support for `Upcoming`, `Active`, and `Ended` contest states, with access controls to hide problems before a contest starts and block submissions after it ends.
*   **Configuration & UX:**
    *   Configurable cooldowns for submissions, IDE runs, and test case generation.
    *   Persistent in-browser code editor state that saves code per problem as the user types.
*   **Comprehensive Logging:** Detailed JSON logs track user activity, submission lifecycle events, and generator requests for auditing and analytics.

## System Architecture

DOJ is built on a layered architecture to ensure separation of concerns and security.

1.  **Web & API Layer (FastAPI):** Handles all HTTP requests, serves the Jinja2 frontend, provides the RESTful JSON API, and manages user authentication.
2.  **Application Logic Layer:** Contains service functions that validate requests, interact with the database, and enqueue tasks.
3.  **Asynchronous Judging Layer (`asyncio`):** A pool of worker tasks continuously pulls submission IDs from a queue and orchestrates the judging workflow.
4.  **Sandbox Engine Layer:** Provides a high-level API to run arbitrary code, handling "compile-if-needed" logic.
5.  **Sandboxing & Measurement Layer:**
    *   **Enforcer (`setrlimit` & `systemd`):** The wrapper script sets the CPU time limit via `setrlimit`. A transient `systemd` scope provides a secondary wall-clock safety net and applies cgroup limits for Memory and Processes.
    *   **Isolator (`bubblewrap`):** Inside the `systemd` scope, `bubblewrap` creates the final sandboxed environment with a minimal, read-only filesystem and no network.
    *   **Measurer (`wrapper.py`):** A lightweight Python script uses `os.wait4()` to precisely measure the **CPU time** (user + system) and peak memory usage of the user's code.

## Getting Started

### Prerequisites

*   A **Linux-based operating system** (for `systemd` and `bubblewrap`).
*   **Python 3.11+**.
*   **`bubblewrap`** (`bwrap`) installed system-wide. On Debian/Ubuntu: `sudo apt-get install bubblewrap`.
*   **`gcc`** and **`g++`** compilers installed for C/C++ support.
*   **`systemd`** user instance capabilities. For running as a system service, [user lingering](https://wiki.archlinux.org/title/Systemd/User#Automatic_start-up_of_systemd_user_instances) must be enabled for the user running the application.

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
    Copy the example environment file, then open the new `.env` file to add your own secret values for Google OAuth and session keys.
    ```bash
    cp .env.example .env
    nano .env
    ```
    You can generate secure keys with the command: `python3 -c 'import secrets; print(secrets.token_hex(32))'`

5.  **Set up the Database:**
    This project uses Alembic for database migrations. Run the following command to create and initialize the database file.
    ```bash
    alembic upgrade head
    ```

6.  **Run the Development Server:**
    ```bash
    uvicorn app.main:app --reload
    ```
    The application will be available at `http://127.0.0.1:8000`.

## Production Deployment

Create a service file at `/etc/systemd/system/doj.service` to manage the Gunicorn process. Remember to replace `<your-username>` and `<UID>`.

```ini
[Unit]
Description=DOJ Gunicorn Instance
After=network.target

[Service]
User=sriv
Group=www-data
WorkingDirectory=/home/sriv/Dockerless-Online-Judge
Environment="PATH=/home/sriv/Dockerless-Online-Judge/.venv/bin:/usr/bin:/bin"
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<UID>/bus"

ExecStart=/home/sriv/Dockerless-Online-Judge/.venv/bin/gunicorn --config gunicorn.conf.py app.main:app

[Install]
WantedBy=multi-user.target
```

To find your UID, run:
```bash
id -u <your-username>
```

**3. Enable and Start the Service:**
```bash
sudo systemctl daemon-reload
sudo systemctl start doj.service
sudo systemctl enable doj.service
```

## Hot-Reloading Contest Data

To add or update contests and problems on a live server without requiring a full application restart, you can use the secure admin reload endpoint.

### Prerequisite: Set the Reload Token

Set the `ADMIN_RELOAD_TOKEN` variable in your `.env` file.

### Workflow

1.  **Update Server Data:** First, update the files on your server inside the `server_data/contests/` directory.
2.  **Trigger the Reload:** Use `curl` to send a POST request to the reload endpoint.
    ```bash
    # Replace YOUR_STATIC_TOKEN_HERE with the value from your .env file
    curl -X POST "https://doj.sriv.in/api/v1/contests/reload" -H "Authorization: Bearer YOUR_STATIC_TOKEN_HERE"
    ```

## Contest & Problem Format

To add content, create directories and files inside the `server_data/contests/` directory.

**Directory Structure:**
```
server_data/
└── contests/
    └── sample-contest/                <-- Contest ID (directory name)
        ├── index.md                   <-- Contest description (Markdown)
        ├── settings.json              <-- Contest settings
        └── palindrome-problem/        <-- Problem ID (directory name)
            ├── index.md               <-- Problem description (Markdown)
            ├── settings.json          <-- Problem settings
            ├── generator.py           <-- (Optional) Test case generator
            ├── validator.py           <-- (Optional) Custom validator
            └── tests/                 <-- Folder for all test cases
                ├── 01-small.in        <-- Test case input
                ├── 01-small.out       <-- Test case output
                └── ...
```

### Contest `settings.json`
This file configures the overall contest.
```json
{
  "title": "My Sample Contest",
  "start_time": "2024-08-01T12:00:00Z",
  "duration_minutes": 120
}
```
*   `start_time` and `duration_minutes` are optional. If omitted, the contest is always active. `start_time` must be a full ISO 8601 string with timezone information (e.g., 'Z' for UTC).

### Problem `settings.json`
This file configures the behavior of a single problem.

```json
{
  "title": "Palindrome Creation",
  "time_limit_sec": 1,
  "memory_limit_mb": 64,
  "allowed_languages": ["python", "c++"],
  "submission_cooldown_sec": 10,
  "generator_cooldown_sec": 5,
  "validator_language": "python",
  "validator_time_limit_sec": 5,
  "validator_memory_limit_mb": 64
}
```
*   The judge will automatically detect `validator.py` and `generator.py` files. If no validator is provided, it defaults to a standard `diff` check against the `.out` files.

### Custom Validator
A validator is a script that determines if a user's output is correct. It is essential for problems with multiple valid solutions.

*   **Interface:** The validator script receives three file paths as command-line arguments:
    1.  `sys.argv[1]`: Path to the problem's input file (e.g., `test.in`).
    2.  `sys.argv[2]`: Path to the user's output file (`user.out`).
    3.  `sys.argv[3]`: Path to the official/expected output file (`test.out`).
*   **Verdict:** The verdict is determined by the validator's **exit code**:
    *   **Exit Code 0:** Accepted (AC)
    *   **Any non-zero Exit Code:** Wrong Answer (WA)
    *   If the validator itself fails to execute (e.g., times out, runs out of memory, or has a syntax error), it will result in an Internal Error (IE) for the submission.

**Example `validator.py` snippet:**
```python
import sys

def main():
    problem_input_path = sys.argv[1]
    user_output_path = sys.argv[2]
    expected_output_path = sys.argv[3]
    
    # ... read files and perform validation logic ...
    
    if is_correct:
        sys.exit(0)  # Accepted
    else:
        sys.exit(1)  # Wrong Answer
```

### Test Case Generator
A generator script allows users to create sample test cases from the UI.
* **Interface:** The generator script should be self-contained and not require any input.
* **Output:**
    *   Content written to `stdout` becomes the **sample input**.
    *   Content written to `stderr` becomes the **sample output**.

## Roadmap

*   **Core Judge:**
    *   Support for more programming languages.
    *   Support for interactive problems.
*   **UI/UX:**
    *   Real-time submission status updates via WebSockets or Server-Sent Events (currently uses periodic polling).
    *   Live contest leaderboards.
    *   Post-contest statistics and ability to view others' solutions.
*   **Backend & Deployment:**
    *   Admin dashboard for managing users and contests.
    *   Support for PostgreSQL as a production database backend.
    *   Official deployment guides and scripts.

## Contributing

Contributions are welcome! Please feel free to open an issue to discuss a new feature or submit a pull request for a bug fix.
