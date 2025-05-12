# locustfile.py

import os
import uuid # Import uuid to generate unique emails
from locust import HttpUser, task, between

# --- Configuration ---
# !! IMPORTANT: Replace with ACTUAL IDs from your system if not using defaults !!
EXISTING_CONTEST_ID = os.getenv("LOCUST_CONTEST_ID", "sample_contest_1")
EXISTING_PROBLEM_ID = os.getenv("LOCUST_PROBLEM_ID", "problem_1")
TARGET_HOST = os.getenv("LOCUST_TARGET_HOST", "http://127.0.0.1:8000")
BASE_API_PATH = "/api/v1" # Define base path for clarity

# Code snippets designed to fail
PYTHON_TLE_CODE = "while True: pass"
PYTHON_MLE_CODE = "a = []\nwhile True:\n    try:\n        # Allocate ~1MB chunks\n        a.append('A' * 1024 * 1024)\n    except MemoryError:\n        # Keep running even after MemoryError to ensure MLE triggers\n        while True: pass"

class SubmissionStressUser(HttpUser):
    """
    User class that registers, logs in, and continuously submits TLE/MLE code
    to stress the submission processing queue and resource limits.
    """
    # Wait 1 to 3 seconds between tasks
    wait_time = between(1, 3)
    host = TARGET_HOST

    # --- User-specific state ---
    auth_token = None
    user_uuid = None
    test_email = None
    test_password = "testpassword123" # Use a fixed password for simplicity

    def on_start(self):
        """
        Runs once per user instance.
        Generates unique credentials, attempts registration, then logs in.
        """
        self.user_uuid = uuid.uuid4()
        self.test_email = f"testuser_{self.user_uuid}@example.com"
        print(f"User starting: Attempting registration for {self.test_email}")

        # --- 1. Attempt Registration ---
        registration_payload = {
            "email": self.test_email,
            "password": self.test_password
        }
        registration_successful = False
        with self.client.post(
            f"{BASE_API_PATH}/auth/register",
            json=registration_payload, # Register endpoint expects JSON
            catch_response=True,
            name=f"{BASE_API_PATH}/auth/register"
        ) as response:
            if response.status_code == 200: # Assuming 200 OK on successful registration
                print(f"Registration successful for {self.test_email}")
                registration_successful = True
                response.success()
            elif response.status_code == 400 and "already exists" in response.text.lower():
                 # Handle case where user might already exist (e.g., from previous test run)
                 print(f"Registration skipped for {self.test_email}: User already exists (HTTP 400). Will attempt login.")
                 # We can still try to log in if they already exist
                 registration_successful = True # Treat as "ok to proceed to login"
                 response.success() # Mark as success for Locust stats, as it's an expected outcome in some scenarios
            else:
                response.failure(f"Registration failed for {self.test_email}: HTTP {response.status_code} - {response.text}")
                registration_successful = False

        # --- 2. Attempt Login (only if registration seemed okay) ---
        if registration_successful:
            print(f"Attempting login for {self.test_email}...")
            login_payload = {"username": self.test_email, "password": self.test_password}
            with self.client.post(
                f"{BASE_API_PATH}/auth/token",
                data=login_payload, # Login endpoint expects form data
                catch_response=True,
                name=f"{BASE_API_PATH}/auth/token (login)"
            ) as response:
                if response.status_code == 200:
                    try:
                        self.auth_token = response.json()["access_token"]
                        print(f"Login successful for {self.test_email}")
                        response.success()
                    except (KeyError, ValueError) as e:
                        response.failure(f"Login succeeded for {self.test_email} but failed to parse token: {e} - Response: {response.text}")
                        self.auth_token = None
                else:
                    response.failure(f"Login failed for {self.test_email}: HTTP {response.status_code} - {response.text}")
                    self.auth_token = None
        else:
            print(f"Skipping login for {self.test_email} due to registration failure.")
            self.auth_token = None # Ensure token is None if registration failed

        if not self.auth_token:
             print(f"User {self.test_email} failed to complete startup (register/login). Will not perform submission tasks.")
             # Optionally stop the user entirely if startup fails
             # self.environment.runner.stop() # or self.stop() in newer Locust versions


    def _get_auth_headers(self):
        """Helper to get authorization headers."""
        if self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        return {}

    def _submit_code(self, language: str, code: str, expected_status_name: str):
        """Helper function to submit code."""
        if not self.auth_token:
            # Log a custom failure if the user isn't logged in (failed on_start)
            self.environment.runner.stats.log_request(
                request_type="SUBMIT",
                name=f"SKIP_{expected_status_name}_{language}",
                response_time=0,
                response_length=0,
                exception="UserNotLoggedInOrRegistered"
            )
            # print(f"Skipping submission for {self.test_email}: Not logged in.") # Can be noisy
            return # Don't proceed if not logged in

        headers = self._get_auth_headers()
        submission_payload = {
            "problem_id": EXISTING_PROBLEM_ID,
            "contest_id": EXISTING_CONTEST_ID,
            "language": language,
            "code": code
        }

        # Use a descriptive name for Locust reporting
        request_name = f"{BASE_API_PATH}/submissions ({expected_status_name}_{language})"

        # The submission endpoint expects JSON payload
        with self.client.post(
            f"{BASE_API_PATH}/submissions/",
            json=submission_payload,
            headers=headers,
            catch_response=True,
            name=request_name
        ) as response:
            # Your API returns 202 Accepted on successful enqueue
            if response.status_code == 202:
                response.success()
            else:
                response.failure(f"Submit {expected_status_name} failed with HTTP {response.status_code}: {response.text}")

    # --- Submission Tasks ---
    # These tasks will only run effectively if the user successfully
    # registered AND logged in during on_start.

    @task(1) # Weight 1: Submit TLE code
    def submit_python_tle(self):
        self._submit_code("python", PYTHON_TLE_CODE, "PY_TLE")

    @task(1) # Weight 1: Submit MLE code
    def submit_python_mle(self):
        self._submit_code("python", PYTHON_MLE_CODE, "PY_MLE")

# --- How to Run ---
# 1. Save as locustfile.py
# 2. Ensure Locust is installed (`pip install locust`)
# 3. Set environment variables if needed:
#    export LOCUST_CONTEST_ID="your_actual_contest_id"
#    export LOCUST_PROBLEM_ID="your_actual_problem_id"
#    export LOCUST_TARGET_HOST="http://your.judge.url"
# 4. Run from terminal: `locust -f locustfile.py`
# 5. Open browser to http://localhost:8089
# 6. Configure users/spawn rate and start swarming.
# 7. Monitor server resources (CPU, RAM, DB connections) and Locust stats.