# Dockerless Online Judge (DOJ)

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Framework](https://img.shields.io/badge/Framework-FastAPI-green.svg)](https://fastapi.tiangolo.com/)

A secure, high-performance, self-hosted online judge built with FastAPI. It leverages a robust, multi-layered sandboxing mechanism using `systemd` scopes and `bubblewrap` for resource control and isolation, eliminating the need for Docker or other containerization overhead.

## Overview

The Dockerless Online Judge (DOJ) provides a complete platform for hosting competitive programming contests. It features a clean web interface for users and a RESTful API for programmatic access. The core of the system is its unique sandboxing architecture, which uses low-level Linux features to securely compile and execute untrusted user code with precise resource measurement and control.

Contests and problems are defined through a simple filesystem structure, making content management straightforward and version-controllable.

## Core Features

*   **User Authentication:** Secure registration, login, and session management via HTTP-only cookies for the UI and Bearer tokens for the API.
*   **Filesystem-based Content:** Contests and problems are loaded directly from a structured directory of Markdown and JSON files. Includes a secure admin endpoint for hot-reloading data without server restarts.
*   **Multi-language Support:** Out-of-the-box support for `C++`, `C`, and `Python`. The architecture is easily extendable to other languages.
*   **Secure Sandboxed Execution:** A multi-layered security model to safely run untrusted code:
    *   **Resource Enforcement (`systemd`):** Hard limits on wall-clock time (TLE), memory usage (MLE), and process count (preventing fork bombs) are enforced at the kernel level using cgroups managed by `systemd`.
    *   **Filesystem & Network Isolation (`bubblewrap`):** User code is executed in a tightly sealed container with no network access (`--unshare-net`) and a read-only view of essential system libraries. It can only read its input and write to its designated output files.
*   **Accurate Resource Measurement:** A dependency-free Python wrapper script uses the `os.fork()` and `os.wait4()` syscalls to precisely measure the wall-clock time and peak memory usage of user submissions, providing results consistent with professional judging platforms.
*   **Asynchronous Judging:** Submissions are pushed to a high-performance `asyncio` queue and processed by a pool of background workers, ensuring the web interface remains fast and responsive under load.
*   **Contest Lifecycle Management:** Full support for `Upcoming`, `Active`, and `Ended` contest states, with access controls to hide problems before a contest starts and block submissions after it ends.
*   **Test Case Generator:** Problems can include a `generator.py` script. Users can request a sample test case (input/output) via the UI, which is securely executed in the same sandboxing environment.
*   **Comprehensive Logging:** Detailed JSON logs track user activity, submission lifecycle events, and generator requests for auditing and analytics.
*   **RESTful API:** A well-defined API for core functionalities like submitting code, checking submission status, and retrieving problem details.

## System Architecture

DOJ is built on a layered architecture to ensure separation of concerns and security.

1.  **Web & API Layer (FastAPI):** Handles all HTTP requests, serves the Jinja2 frontend, provides the RESTful JSON API, and manages user authentication.
2.  **Application Logic Layer:** Contains service functions (`submission_service`, `contest_service`, etc.). On a new submission, it performs validation, creates a database record, and enqueues the submission ID.
3.  **Asynchronous Judging Layer (`asyncio`):** A pool of worker tasks continuously pulls submission IDs from the queue and orchestrates the judging process for each one.
4.  **Sandboxing & Measurement Layer:**
    *   **Enforcer (`systemd`):** A transient `systemd` scope applies non-negotiable cgroup limits for Time, Memory, and Processes.
    *   **Isolator (`bubblewrap`):** Inside the `systemd` scope, `bubblewrap` creates the final sandboxed environment with a minimal, read-only filesystem and no network.
    *   **Measurer (`wrapper.py`):** A dynamically-generated Python script uses `os.fork()` and `os.wait4()` to execute the user's code and precisely measure its wall-clock time and peak memory usage.
    *   **Collector:** The main application reads the measurement results and the `systemd` exit status to determine the final verdict (Accepted, Wrong Answer, TLE, etc.).

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
    Copy the example environment file, then open the new `.env` file to add your own secret values.
    ```bash
    cp .env.example .env
    nano .env
    ```
    You can generate secure keys with the command: `python3 -c 'import secrets; print(secrets.token_hex(32))'`

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

## Hot-Reloading Contest Data

To add or update contests and problems on a live server without requiring a full application restart, you can use the secure admin reload endpoint.

### Prerequisite: Set the Reload Key

This feature requires you to set the `ADMIN_RELOAD_KEY` variable in your `.env` file.

1.  Generate a strong, random token:
    ```bash
    python3 -c 'import secrets; print(secrets.token_hex(32))'
    ```
2.  Add it to your `.env` file:
    ```env
    ADMIN_RELOAD_TOKEN=your_generated_secret_token_here
    ```

### Workflow

1.  **Update Server Data:** First, update the files on your server inside the `server_data/contests/` directory. You can do this using `git pull`, `scp`, `rsync`, or by manually editing the files.

2.  **Trigger the Reload:** Next, from your server's command line (or any machine), use `curl` to send a POST request to the reload endpoint, providing your static token as a Bearer token.
    ```bash
    # Replace YOUR_STATIC_TOKEN_HERE with the value from your .env file
    curl -X POST "https://doj.sriv.in/api/v1/contests/reload" \
         -H "Authorization: Bearer YOUR_STATIC_TOKEN_HERE"
    ```

3.  **Verify:** If successful, the server will respond with `{"message":"Contest data reload initiated successfully."}`. The new contest data is now live.

## Contest & Problem Format

To add content, create directories and files inside the `server_data/contests/` directory.

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
            ├── test1.in               <-- Test case input
            ├── test1.out              <-- Test case output
            └── ...                    <-- More test cases
```
See the example contests in the `server_data` directory for more clarity.

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
