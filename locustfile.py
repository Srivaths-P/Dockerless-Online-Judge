import os
import random
import uuid
from locust import HttpUser, task, constant

TARGET_HOST = os.getenv("LOCUST_TARGET_HOST", "http://127.0.0.1:8000")
CONTEST_ID = os.getenv("LOCUST_CONTEST_ID", "Contest3")
CHRONOS_ID = "chronos"
REPLAY_ID = "replay"
BASE_API_PATH = "/api/v1"

AC_CHRONOS_PYTHON = "s = input().strip().lower()\nprint('YES' if s == s[::-1] else 'NO')"
AC_REPLAY_PYTHON = """
from collections import Counter
import random
try:
    freq = list(map(int, input().split()))
    if len(freq) != 26:
        print("-1")
    else:
        odd_chars = sum(1 for f in freq if f % 2 != 0)
        if odd_chars > 1:
            print("-1")
        else:
            ans, mid = "", ""
            for i in range(26):
                if freq[i] % 2 != 0:
                    mid = chr(ord('a') + i)
                ans += chr(ord('a') + i) * (freq[i] // 2)
            res = list(ans)
            random.shuffle(res)
            ans = "".join(res)
            print(ans + mid + ans[::-1])
except:
    print("-1")
"""
WA_CHRONOS_PYTHON = "print('This is the wrong answer')"
WA_REPLAY_PYTHON = "print('notapalindrome')"
TLE_PYTHON = "while True: pass"
TLE_CPP = "#include <iostream>\nint main() { while(true); return 0; }"
MLE_PYTHON = "a = []\nwhile True: a.append('A' * 1024 * 1024)"
MLE_CPP = "#include <vector>\n#include <string>\nint main() { std::vector<std::string> v; while(true){ v.push_back(std::string(1024*1024, 'A')); } }"
RE_PYTHON_DIV_ZERO = "print(1/0)"
RE_CPP_SEGFAULT = "int main() { int *p = nullptr; *p = 42; return 0; }"
FORK_BOMB_PYTHON = "import os\nwhile True: os.fork()"
FORK_BOMB_CPP = "#include <unistd.h>\nint main() { while(true){ fork(); } return 0; }"
CE_CPP = "int main() { int x = ; return 0; }"
COMPILE_BOMB_CPP = "#include <iostream>\ntemplate<int N> struct C { C<N-1> c; };\ntemplate<> struct C<0> {};\nint main() { C<20000> c; std::cout << \"Done\"; return 0; }"


class JudgingUser(HttpUser):
    host = TARGET_HOST

    wait_time = constant(5.1)

    def on_start(self):
        unique_id = uuid.uuid4().hex[:12]
        self.username = f"locust_user_{unique_id}@example.com"
        self.password = "password"
        self.auth_token = None

        with self.client.post(
                f"{BASE_API_PATH}/auth/register",
                json={"email": self.username, "password": self.password},
                name=f"{BASE_API_PATH}/auth/register",
                catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Registration failed for {self.username} with status {response.status_code}: {response.text}")
                return

        with self.client.post(
                f"{BASE_API_PATH}/auth/token",
                data={"username": self.username, "password": self.password},
                name=f"{BASE_API_PATH}/auth/token (login after register)",
                catch_response=True
        ) as response:
            if response.status_code == 200:
                self.auth_token = response.json().get("access_token")
                if not self.auth_token:
                    response.failure(f"Login successful for {self.username} but no token was returned.")
            else:
                response.failure(
                    f"Login failed for newly registered user {self.username} with status {response.status_code}: {response.text}")

    def _submit_code(self, problem_id: str, language: str, code: str, name_suffix: str):
        if not self.auth_token:
            return

        headers = {"Authorization": f"Bearer {self.auth_token}"}
        payload = {
            "problem_id": problem_id,
            "contest_id": CONTEST_ID,
            "language": language,
            "code": code,
        }

        request_name = f"{BASE_API_PATH}/submissions ({problem_id}_{name_suffix})"

        with self.client.post(
                f"{BASE_API_PATH}/submissions/",
                json=payload,
                headers=headers,
                name=request_name,
                catch_response=True
        ) as response:
            if response.status_code != 202:
                response.failure(f"Submit failed for {request_name} with status {response.status_code}")

    @task(10)
    def submit_chronos_ac(self):
        self._submit_code(CHRONOS_ID, "python", AC_CHRONOS_PYTHON, "AC_PY")

    @task(10)
    def submit_replay_ac(self):
        self._submit_code(REPLAY_ID, "python", AC_REPLAY_PYTHON, "AC_PY")

    @task(5)
    def submit_chronos_wa(self):
        self._submit_code(CHRONOS_ID, "python", WA_CHRONOS_PYTHON, "WA_PY")

    @task(5)
    def submit_replay_wa(self):
        self._submit_code(REPLAY_ID, "python", WA_REPLAY_PYTHON, "WA_PY")

    @task(3)
    def submit_python_tle(self):
        problem = random.choice([CHRONOS_ID, REPLAY_ID])
        self._submit_code(problem, "python", TLE_PYTHON, "TLE_PY")

    @task(3)
    def submit_cpp_tle(self):
        problem = random.choice([CHRONOS_ID, REPLAY_ID])
        self._submit_code(problem, "c++", TLE_CPP, "TLE_CPP")

    @task(2)
    def submit_python_mle(self):
        problem = random.choice([CHRONOS_ID, REPLAY_ID])
        self._submit_code(problem, "python", MLE_PYTHON, "MLE_PY")

    @task(2)
    def submit_cpp_mle(self):
        problem = random.choice([CHRONOS_ID, REPLAY_ID])
        self._submit_code(problem, "c++", MLE_CPP, "MLE_CPP")

    @task(2)
    def submit_python_re(self):
        problem = random.choice([CHRONOS_ID, REPLAY_ID])
        self._submit_code(problem, "python", RE_PYTHON_DIV_ZERO, "RE_PY")

    @task(2)
    def submit_cpp_re(self):
        problem = random.choice([CHRONOS_ID, REPLAY_ID])
        self._submit_code(problem, "c++", RE_CPP_SEGFAULT, "RE_CPP")

    @task(1)
    def submit_python_fork_bomb(self):
        problem = random.choice([CHRONOS_ID, REPLAY_ID])
        self._submit_code(problem, "python", FORK_BOMB_PYTHON, "FORK_BOMB_PY")

    @task(1)
    def submit_cpp_fork_bomb(self):
        problem = random.choice([CHRONOS_ID, REPLAY_ID])
        self._submit_code(problem, "c++", FORK_BOMB_CPP, "FORK_BOMB_CPP")

    @task(2)
    def submit_cpp_ce(self):
        problem = random.choice([CHRONOS_ID, REPLAY_ID])
        self._submit_code(problem, "c++", CE_CPP, "CE_CPP")

    @task(1)
    def submit_cpp_compile_bomb(self):
        problem = random.choice([CHRONOS_ID, REPLAY_ID])
        self._submit_code(problem, "c++", COMPILE_BOMB_CPP, "COMPILE_BOMB_CPP")
