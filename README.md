# Dockerless Online Judge (DOJ)

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Framework](https://img.shields.io/badge/Framework-FastAPI-green.svg)](https://fastapi.tiangolo.com/)

A secure, high-performance, self-hosted online judge built with FastAPI. It leverages a robust, multi-layered sandboxing mechanism using `systemd` scopes and `bubblewrap` for resource control and isolation, eliminating the need for Docker or other containerization overhead.

## Overview

The Dockerless Online Judge (DOJ) provides a complete platform for hosting competitive programming contests. It features a clean web interface for users and a RESTful API for programmatic access. The core of the system is its unique sandboxing architecture, which uses low-level Linux features to securely compile and execute untrusted user code with precise resource measurement and control.

Contests and problems are defined through a simple filesystem structure, making content management straightforward and version-controllable.

## Core Features

*   **User Authentication:** Secure registration, login, and session management via HTTP-only cookies for the UI and Bearer tokens for the API.
*   **Filesystem-based Content:** Contests and problems are loaded directly from a structured directory of Markdown and JSON files, allowing for easy updates and versioning with Git.
*   **Multi-language Support:** Out-of-the-box support for `C++`, `C`, and `Python`. The architecture is easily extendable to other languages.
*   **Secure Sandboxed Execution:** A multi-layered security model to safely run untrusted code:
    *   **Resource Enforcement (`systemd`):** Hard limits on wall-clock time (TLE), memory usage (MLE), and process count (preventing fork bombs) are enforced at the kernel level using cgroups managed by `systemd`.
    *   **Filesystem & Network Isolation (`bubblewrap`):** User code is executed in a tightly sealed container with no network access (`--unshare-net`) and a read-only view of essential system libraries. It can only read its input and write to its designated output files.
*   **Accurate Resource Measurement:** A dependency-free Python wrapper script uses the `os.fork()` and `os.wait4()` syscalls to precisely measure the wall-clock time and peak memory usage of user submissions, providing results consistent with professional judging platforms.
*   **Asynchronous Judging:** Submissions are pushed to a high-performance `asyncio` queue and processed by a pool of background workers, ensuring the web interface remains fast and responsive under load.
*   **Test Case Generator:** Problems can include a `generator.py` script. Users can request a sample test case (input/output) via the UI, which is securely executed in the same sandboxing environment.
*   **Comprehensive Logging:** Detailed JSON logs track user activity, submission lifecycle events, and generator requests for auditing and analytics.
*   **RESTful API:** A well-defined API for core functionalities like submitting code, checking submission status, and retrieving problem details.

## System Architecture

DOJ is built on a layered architecture to ensure separation of concerns and security.

1.  **Web & API Layer (FastAPI):**
    *   Handles all HTTP requests.
    *   Serves the Jinja2-rendered HTML frontend.
    *   Provides the RESTful JSON API.
    *   Manages user authentication and sessions.

2.  **Application Logic Layer:**
    *   Contains the service functions (`submission_service`, `contest_service`, etc.).
    *   On a new submission, it performs validation (cooldowns, allowed languages), creates a record in the database, and enqueues the submission ID into the `asyncio` queue.

3.  **Asynchronous Judging Layer (`asyncio`):**
    *   A pool of worker tasks continuously pulls submission IDs from the queue.
    *   For each submission, a worker fetches the details from the database and invokes the sandboxing layer to compile and run the code against each test case.

4.  **Sandboxing & Measurement Layer:**
    *   **Enforcer (`systemd`):** A transient `systemd` scope is created for each execution, which applies non-negotiable cgroup limits for `RuntimeMaxSec` (Time Limit) and `MemoryMax` (Memory Limit).
    *   **Isolator (`bubblewrap`):** Inside the `systemd` scope, `bubblewrap` creates the final sandboxed environment with a minimal, read-only filesystem and no network access.
    *   **Measurer (`wrapper.py`):** `bubblewrap`'s entry point is a small, dynamically-generated Python script. This script uses `os.fork()` and `os.wait4()` to execute the user's code as a child process and precisely measure its wall-clock time and peak memory usage upon termination. This data is written to a results file.
    *   **Collector:** The main application reads the results file and the `systemd` exit status to determine the final verdict (Accepted, Wrong Answer, TLE, MLE, etc.).

## Getting Started

### Prerequisites

*   A **Linux-based operating system** (for `systemd` and `bubblewrap`).
*   **Python 3.11+**.
*   **`bubblewrap`** (`bwrap`) installed system-wide.
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
    Copy the example environment file and fill in your own secret values.
    ```bash
    cp .env.example .env
    ```
    Now, open the newly created `.env` file and generate your secrets.  
    You can use the following command to generate a secure key: `python -c 'import secrets; print(secrets.token_hex(32))'`

5.  **Set up the Database:**
    This project uses Alembic for database migrations. Run the following command to create and initialize the `judge.db` file.
    ```bash
    alembic upgrade head
    ```

6.  **Run the Development Server:**
    ```bash
    uvicorn app.main:app --reload
    ```
    The application will be available at `http://127.0.0.1:8000`.

## Contest & Problem Format

To add content, create directories and files inside the `server_data/contests/` directory. The application loads all content from this path on startup.

The expected structure is as follows:

```
server_data/
└── contests/
    └── sample-contest/                <-- Contest ID (directory name)
        ├── index.md                   <-- Contest description (Markdown)
        ├── settings.json              <-- Contest settings
        └── a-plus-b/                  <-- Problem ID (directory name)
            ├── index.md               <-- Problem description (Markdown)
            ├── settings.json          <-- Problem settings
            ├── generator.py           <-- (Optional) Test case generator
            ├── test1.in               <-- test case input
            ├── test1.out              <-- test case output
            └── ...                    <-- more test cases
```
See the example contests in the `server_data` directory for more clarity.

### `settings.json` examples

**Contest `settings.json`:**
```json
{
  "title": "My First Contest",
  "start_time": "2024-01-01T00:00:00Z",
  "duration_minutes": 120
}
```

**Problem `settings.json`:**
```json
{
  "title": "A + B",
  "time_limit_sec": 1,
  "memory_limit_mb": 64,
  "allowed_languages": ["python", "c++"],
  "submission_cooldown_sec": 10,
  "generator_cooldown_sec": 5,
  "generator_time_limit_sec": 2,
  "generator_memory_limit_mb": 128
}
```

## Roadmap

*   **Core Judge:**
    *   Support for more programming languages.
    *   Custom checkers for problems with multiple correct outputs.
    *   Support for interactive problems.
*   **UI/UX:**
    *   Real-time submission status updates via WebSockets or Server-Sent Events.
    *   Live contest leaderboards.
    *   Post-contest statistics and ability to view others' solutions.
*   **Backend & Deployment:**
    *   Admin dashboard for managing users and contests.
    *   Support for PostgreSQL as a production database backend.
    *   Official deployment guides and scripts.
