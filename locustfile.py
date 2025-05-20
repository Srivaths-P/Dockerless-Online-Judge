import os

from locust import HttpUser, task, between

EXISTING_CONTEST_ID = os.getenv("LOCUST_CONTEST_ID", "sample_contest_1")
EXISTING_PROBLEM_ID = os.getenv("LOCUST_PROBLEM_ID", "problem_1")
TARGET_HOST = os.getenv("LOCUST_TARGET_HOST", "http://127.0.0.1:8000")
BASE_API_PATH = "/api/v1"

PYTHON_TLE_CODE = "while True: pass"
PYTHON_MLE_CODE = "a = []\nwhile True:\n    try:\n        # Allocate ~1MB chunks\n        a.append('A' * 1024 * 1024)\n    except MemoryError:\n        # Keep running even after MemoryError to ensure MLE triggers\n        while True: pass"
PYTHON_RE_CODE_DIV_ZERO = "print(1/0)"
PYTHON_WA_CODE = "print('This is the wrong answer!')"


class SubmissionUser(HttpUser):
    wait_time = between(1, 3)
    host = TARGET_HOST

    username = "asd@asd.com"
    password = "asd@asd.com"

    auth_token = None

    def on_start(self):
        print(f"User starting: Attempting login for {self.username}")

        login_payload = {"username": self.username, "password": self.password}
        with self.client.post(
                f"{BASE_API_PATH}/auth/token",
                data=login_payload,
                catch_response=True,
                name=f"{BASE_API_PATH}/auth/token (login)"
        ) as response:
            if response.status_code == 200:
                try:
                    self.auth_token = response.json()["access_token"]
                    print(f"Login successful for {self.username}")
                    response.success()
                except (KeyError, ValueError) as e:
                    response.failure(
                        f"Login succeeded but failed to parse token for {self.username}: {e} - Response: {response.text}")
                    self.auth_token = None
            else:
                response.failure(f"Login failed for {self.username}: HTTP {response.status_code} - {response.text}")
                self.auth_token = None
                print(f"Login failed for {self.username}. This user instance will not submit.")

    def _get_auth_headers(self):
        if self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        return {}

    def _submit_code(self, language: str, code: str, expected_status_name: str):
        if not self.auth_token:
            self.environment.runner.stats.log_error(
                "SUBMISSION_SKIPPED",
                f"{BASE_API_PATH}/submissions ({expected_status_name}_{language})",
                f"User {self.username} Not Logged In (Login Failed)"
            )
            return

        headers = self._get_auth_headers()
        submission_payload = {
            "problem_id": EXISTING_PROBLEM_ID,
            "contest_id": EXISTING_CONTEST_ID,
            "language": language,
            "code": code
        }

        request_name = f"{BASE_API_PATH}/submissions ({expected_status_name}_{language})"

        with self.client.post(
                f"{BASE_API_PATH}/submissions/",
                json=submission_payload,
                headers=headers,
                catch_response=True,
                name=request_name
        ) as response:
            if response.status_code == 202:
                response.success()
            else:
                response.failure(
                    f"Submit {expected_status_name} failed with HTTP {response.status_code}: {response.text}")

    @task(2)
    def submit_python_tle(self):
        self._submit_code("python", PYTHON_TLE_CODE, "PY_TLE")

    @task(2)
    def submit_python_mle(self):
        self._submit_code("python", PYTHON_MLE_CODE, "PY_MLE")

    @task(1)
    def submit_python_re(self):
        self._submit_code("python", PYTHON_RE_CODE_DIV_ZERO, "PY_RE")

    @task(1)
    def submit_python_wa(self):
        self._submit_code("python", PYTHON_WA_CODE, "PY_WA")
