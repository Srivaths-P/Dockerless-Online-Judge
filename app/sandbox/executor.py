# In app/sandbox/executor.py
import asyncio
import os
import resource
import shutil
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, List # Added List for queue
import json
import traceback # Added for queue error logging

from sqlalchemy.orm import Session

# Adjust these imports based on your project structure
from app.crud import crud_submission
from app.db.session import SessionLocal # Use SessionLocal for worker sessions
from app.schemas.problem import Problem, TestCase
from app.schemas.submission import SubmissionStatus, TestCaseResult
from app.services.contest_service import get_problem_by_id

# --- Configuration for sandboxed code execution (User Provided) ---
BWRAP = "/usr/bin/bwrap"
PYTHON3 = "/usr/bin/python3"
GCC = "/usr/bin/gcc"
GPP = os.getenv("GPP_PATH", "/usr/bin/g++")

LANGUAGE_CONFIG: Dict[str, Dict[str, Any]] = {
    "python": {
        "ext": ".py",
        "compile": None,
        "run": [PYTHON3, "/sandbox/user_code.py"]
    },
    "c": {
        "ext": ".c",
        "compile": [GCC, "/sandbox/user_code.c", "-o", "/sandbox/user_exec",
                    "-O2", "-std=c11", "-lm"],
        "run": ["/sandbox/user_exec"]
    },
    "c++": {
        "ext": ".cpp",
        "compile": [GPP, "/sandbox/user_code.cpp", "-o", "/sandbox/user_exec",
                    "-O2", "-std=c++17"],
        "run": ["/sandbox/user_exec"]
    },
}

# --- Thread pool for blocking calls within run_code_in_sandbox (User Provided) ---
MAX_THREADS = (os.cpu_count() or 2) * 2
# Renamed to avoid potential conflicts if 'executor' is used elsewhere
blocking_executor = ThreadPoolExecutor(max_workers=MAX_THREADS)

# --- REMOVED User's old SubmissionQueue class ---

# --- Helper functions for bwrap + systemd-run (User Provided) ---
def _make_systemd_bwrap_cmd(
        unit: str,
        tlim: int,
        mlim: int,
        bwrap_args: list
) -> list:
    cmd = [
              "systemd-run", "--quiet", "--scope",
              f"--unit={unit}", "--slice=judge.slice",
              "-p", "TasksMax=64",
              "-p", f"RuntimeMaxSec={tlim}",
              "-p", "CPUQuota=100%",
              "-p", f"MemoryMax={mlim}M",
              BWRAP
          ] + bwrap_args
    return cmd


def _systemd_bwrap_run(
        unit: str,
        tlim: int,
        mlim: int,
        bwrap_args: list,
        stdin_path: Optional[str], # Renamed argument for clarity vs user's 'stdin'
        stdout_path: str,          # Renamed argument for clarity vs user's 'stdout'
        stderr_path: str           # Renamed argument for clarity vs user's 'stderr'
) -> Dict[str, Any]:
    # Ensure directories exist before opening files
    os.makedirs(os.path.dirname(stdout_path), exist_ok=True)
    os.makedirs(os.path.dirname(stderr_path), exist_ok=True)

    full_cmd = _make_systemd_bwrap_cmd(unit, tlim, mlim, bwrap_args)

    # Use try/finally to ensure files are closed
    stdin_file = None
    stdout_file = None
    stderr_file = None
    try:
        stdin_file = open(stdin_path, 'rb') if stdin_path else subprocess.DEVNULL
        stdout_file = open(stdout_path, 'wb')
        stderr_file = open(stderr_path, 'wb')

        proc = subprocess.run(
            full_cmd,
            stdin=stdin_file,
            stdout=stdout_file,
            stderr=stderr_file
            # Consider adding timeout=tlim+5 here as a safety net
        )
        exit_code = proc.returncode

    finally:
        if stdin_file and stdin_file != subprocess.DEVNULL:
            stdin_file.close()
        if stdout_file:
            stdout_file.close()
        if stderr_file:
            stderr_file.close()

    # --- Get resource usage and systemd result (User Provided Logic) ---
    # Note: getrusage might not capture usage from systemd-run correctly.
    # Relying on systemd's result is generally better for limits.
    try:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        peak_rss_kb = usage.ru_maxrss
    except Exception as e:
        print(f"Warning: Failed to get resource usage: {e}")
        peak_rss_kb = -1 # Indicate failure

    # Check systemd result
    show = subprocess.run(
        ["systemctl", "show", "-p", "Result", f"{unit}.scope"],
        capture_output=True, text=True, check=False # Don't fail if unit is gone
    )
    _, _, raw = show.stdout.partition("=")
    systemd_result = raw.strip() if show.returncode == 0 else "unknown" # Handle case where unit is gone

    # Attempt to clean up the systemd unit state (User Provided Logic)
    # Removed 'sudo' - systemd-run usually doesn't require sudo for reset-failed if run by same user
    subprocess.run(
        ["systemctl", "reset-failed", f"{unit}.scope"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )

    return {
        "systemd": systemd_result,
        "exit": exit_code,
        "mem_kb": peak_rss_kb # Keep user's memory reporting, though it might be inaccurate
    }


def _diff_files(out_path: str, exp_path: str) -> int:
    # Ensure files exist before diffing
    if not os.path.exists(out_path):
        with open(out_path, 'w') as f: pass # Create empty if missing
    if not os.path.exists(exp_path):
        with open(exp_path, 'w') as f: pass # Create empty if missing

    # Use diff options for common competitive programming scenarios (User Provided Logic)
    cp = subprocess.run(
        ["diff", "-Z", "--strip-trailing-cr", "-q", out_path, exp_path], # Added -q for quiet
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return cp.returncode


# --- run_code_in_sandbox function (User Provided - with minor adjustments for safety/clarity) ---
async def run_code_in_sandbox(
        submission_id: uuid.UUID,
        code: str,
        problem: Problem,
        test_case: TestCase,
        language: str
) -> TestCaseResult:
    lang = language.lower()
    cfg = LANGUAGE_CONFIG.get(lang)
    if not cfg:
        return TestCaseResult(
            test_case_name=test_case.name,
            status=SubmissionStatus.INTERNAL_ERROR,
            stderr=f"Unsupported language: {language}"
        )

    # Use a unique temporary directory name
    td_prefix = f"judge_{submission_id.hex[:8]}_{test_case.name.replace(' ', '_')}_"
    td = tempfile.mkdtemp(prefix=td_prefix)

    try: # Wrap the whole process in try/finally for cleanup
        code_f = os.path.join(td, "user_code" + cfg["ext"])
        in_f = os.path.join(td, "input.txt")
        results_dir = os.path.join(td, "results") # Keep results inside temp dir
        os.makedirs(results_dir, exist_ok=True)
        out_f = os.path.join(results_dir, f"{submission_id.hex}.out") # Use submission hex in name
        err_f = os.path.join(results_dir, f"{submission_id.hex}.err")
        exp_f = os.path.join(results_dir, "expected.txt") # Expected output file

        # Write code and input/expected output
        with open(code_f, 'w', encoding='utf-8') as f:
            f.write(code)
        with open(in_f, 'w', encoding='utf-8') as f:
            if test_case.input_content:
                f.write(test_case.input_content)
        with open(exp_f, 'w', encoding='utf-8') as f:
            if test_case.output_content:
                f.write(test_case.output_content)

        status = SubmissionStatus.INTERNAL_ERROR # Default status
        stderr_msg = None
        exec_ms = 0.0
        mem_kb = None # Initialize memory usage

        # --- Compilation phase (User Provided Logic - adapted paths) ---
        if cfg["compile"]:
            unit_c = f"compile-{submission_id.hex[:8]}-{uuid.uuid4().hex[:4]}" # More unique unit name
            compile_out_f = os.path.join(results_dir, "compile.out") # Separate compile output
            compile_err_f = os.path.join(results_dir, "compile.err") # Separate compile error

            bwrap_args_c = [
                           "--ro-bind", "/usr", "/usr",
                           "--ro-bind", "/lib", "/lib", # Add common lib paths
                           "--ro-bind", "/lib64", "/lib64",
                           "--bind", td, "/sandbox", # Mount temp dir RW
                           "--proc", "/proc",        # Mount /proc
                           "--dev", "/dev",          # Mount /dev
                           "--chdir", "/sandbox",    # Change directory
                           "--unshare-pid",          # Isolate PID
                           "--unshare-net",          # Isolate network
                       ] + cfg["compile"] # Add compile command

            cres = await asyncio.get_running_loop().run_in_executor(
                blocking_executor, # Use the renamed executor
                _systemd_bwrap_run,
                unit_c, 30, 512, # Compile limits: 30s, 512MB
                bwrap_args_c,
                None, compile_out_f, compile_err_f # Pass correct paths
            )

            mem_kb = cres.get("mem_kb", None) # Get memory usage if available

            if cres["systemd"] != "success" or cres["exit"] != 0:
                # Read compile error message
                if os.path.exists(compile_err_f):
                    try:
                        with open(compile_err_f, 'r', encoding='utf-8', errors='ignore') as ef:
                           stderr_msg = ef.read(2048).strip() # Limit error message size
                    except Exception:
                        stderr_msg = "Failed to read compiler error output."
                else:
                    stderr_msg = "Compilation failed (no error output)."

                # Add systemd result info if relevant
                if cres["systemd"] == "timeout":
                     stderr_msg = f"Compilation Timed Out ({stderr_msg})"
                elif cres["systemd"] in ("oom", "memory", "oom-kill"):
                     stderr_msg = f"Compilation Memory Limit Exceeded ({stderr_msg})"

                # Return Compilation Error status
                return TestCaseResult(
                    test_case_name=test_case.name,
                    status=SubmissionStatus.COMPILATION_ERROR,
                    stderr=stderr_msg,
                    execution_time_ms=0.0,
                    memory_used_kb=mem_kb # Report compile memory if available
                )

        # --- Execution phase (User Provided Logic - adapted paths) ---
        unit_e = f"exec-{submission_id.hex[:8]}-{uuid.uuid4().hex[:4]}" # More unique unit name
        bwrap_args_e = [
                       "--ro-bind", "/usr", "/usr",
                       "--ro-bind", "/lib", "/lib",
                       "--ro-bind", "/lib64", "/lib64",
                       "--bind", td, "/sandbox", # Mount temp dir RW
                       "--proc", "/proc",
                       "--dev", "/dev",
                       "--chdir", "/sandbox",
                       "--unshare-pid",
                       "--unshare-net",
                   ] + cfg["run"] # Add run command

        t0 = time.perf_counter_ns()
        eres = await asyncio.get_running_loop().run_in_executor(
            blocking_executor, # Use the renamed executor
            _systemd_bwrap_run,
            unit_e,
            problem.time_limit_sec + 1, # Add buffer for systemd overhead
            problem.memory_limit_mb,
            bwrap_args_e,
            in_f, out_f, err_f # Pass correct paths
        )
        exec_ns = time.perf_counter_ns() - t0

        sysd = eres["systemd"]
        ret = eres["exit"]
        mem_kb = eres.get("mem_kb", None) # Get memory usage if available
        exec_ms = round(exec_ns / 1_000_000, 2)

        # --- Diff check (User Provided Logic - adapted paths) ---
        diffc = -1 # Default diff code (error/not run)
        if sysd == "success" and ret == 0:
            diffc = await asyncio.get_running_loop().run_in_executor(
                blocking_executor, # Use the renamed executor
                _diff_files,
                out_f, exp_f # Diff user output vs expected output
            )

        # --- Map to SubmissionStatus (User Provided Logic) ---
        if sysd == "timeout":
            status = SubmissionStatus.TIME_LIMIT_EXCEEDED
        elif sysd in ("oom", "memory", "oom-kill"):
            status = SubmissionStatus.MEMORY_LIMIT_EXCEEDED
        elif sysd == "success":
            if ret != 0:
                status = SubmissionStatus.RUNTIME_ERROR
            else:
                status = SubmissionStatus.ACCEPTED if diffc == 0 else SubmissionStatus.WRONG_ANSWER
        elif sysd == "failed" and ret != 0:
            status = SubmissionStatus.RUNTIME_ERROR # Treat failed+nonzero as RE
        else:
            status = SubmissionStatus.INTERNAL_ERROR # Catch-all for other systemd failures
            stderr_msg = f"Execution failed (systemd: {sysd}, exit: {ret})"

        # Read stderr only if not Accepted
        if status != SubmissionStatus.ACCEPTED:
            if os.path.exists(err_f):
                try:
                    with open(err_f, 'r', encoding='utf-8', errors='ignore') as ef:
                        stderr_content = ef.read(2048).strip() # Limit stderr size
                        # Prepend existing message if any (e.g., from Internal Error mapping)
                        stderr_msg = f"{stderr_msg}\n{stderr_content}".strip() if stderr_msg else stderr_content
                except Exception:
                    stderr_msg = f"{stderr_msg}\n(Failed to read stderr)".strip() if stderr_msg else "(Failed to read stderr)"

        # Clamp execution time if TLE
        if status == SubmissionStatus.TIME_LIMIT_EXCEEDED:
            exec_ms = float(problem.time_limit_sec * 1000)

        return TestCaseResult(
            test_case_name=test_case.name,
            status=status,
            stdout=None, # Usually don't return stdout
            stderr=stderr_msg,
            execution_time_ms=exec_ms,
            memory_used_kb=mem_kb # Report execution memory if available
        )

    except Exception as e:
        # Catch unexpected errors during sandbox setup/logic
        print(f"!!! Critical error in run_code_in_sandbox setup for {submission_id} !!!")
        traceback.print_exc()
        return TestCaseResult(
            test_case_name=test_case.name,
            status=SubmissionStatus.INTERNAL_ERROR,
            stderr=f"Sandbox setup/internal error: {type(e).__name__}: {e}",
            execution_time_ms=0.0,
            memory_used_kb=None
        )
    finally:
        # Cleanup the temporary directory
        shutil.rmtree(td, ignore_errors=True)


# --- CORRECTED Submission Processing Queue (Integrates with Lifespan) ---
class SubmissionProcessingQueue:
    def __init__(self, worker_count: int):
        self._queue = asyncio.Queue()
        self._worker_count = worker_count
        self._workers: List[asyncio.Task] = [] # To keep track of worker tasks
        print(f"[Queue] Initialized with capacity for {worker_count} workers.")
        # *** DO NOT START WORKERS HERE ***

    async def start_workers(self):
        """Starts the worker tasks. Should be called when an event loop is running."""
        if self._workers:
            print("[Queue] Workers already started.")
            return
        print(f"[Queue] Starting {self._worker_count} workers...")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            print("[Queue] ERROR: Cannot start workers, no running event loop!")
            return

        self._workers = [
            loop.create_task(self._worker(worker_id=i))
            for i in range(self._worker_count)
        ]
        print(f"[Queue] {len(self._workers)} workers created.")

    async def stop_workers(self):
        """Gracefully stops the worker tasks."""
        if not self._workers:
            print("[Queue] No workers to stop.")
            return
        print("[Queue] Stopping workers...")
        for _ in self._workers:
            await self._queue.put(None) # Sentinel value
        print("[Queue] Waiting for workers to finish...")
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        print("[Queue] All workers stopped.")
        while not self._queue.empty(): # Clear any remaining sentinels
            try:
                item = self._queue.get_nowait()
                print(f"[Queue] Discarding item from queue during shutdown: {item}")
                self._queue.task_done()
            except asyncio.QueueEmpty: break
        print("[Queue] Shutdown complete.")

    async def enqueue(self, submission_id: str):
        """Called by submission_service—returns immediately."""
        if not self._workers:
            print("[Queue] WARNING: Enqueuing submission, but workers are not running!")
        await self._queue.put(submission_id)
        print(f"[Queue] Enqueued submission {submission_id[:8]}... Queue size: {self._queue.qsize()}")

    async def _worker(self, worker_id: int):
        print(f"[Worker {worker_id}] Starting...")
        while True:
            submission_id = await self._queue.get()
            if submission_id is None: # Sentinel check
                print(f"[Worker {worker_id}] Received stop signal. Exiting.")
                self._queue.task_done()
                break
            print(f"[Worker {worker_id}] Processing submission {submission_id[:8]}...")
            start_time = time.monotonic()
            try:
                await self._process_submission(submission_id, worker_id)
            except Exception as e:
                print(f"[Worker {worker_id}] CRITICAL ERROR processing {submission_id[:8]}: {type(e).__name__} - {e}")
                traceback.print_exc()
                await self._mark_submission_internal_error(submission_id, f"Worker processing failed: {e}")
            end_time = time.monotonic()
            print(f"[Worker {worker_id}] Finished submission {submission_id[:8]} in {end_time - start_time:.2f}s. Queue size: {self._queue.qsize()}")
            self._queue.task_done()
        print(f"[Worker {worker_id}] Stopped.")

    async def _process_submission(self, submission_id: str, worker_id: int):
        """Contains the logic to fetch, run, and update a single submission."""
        db: Optional[Session] = None
        sub = None
        try:
            db = SessionLocal() # Create a new session for this task
            # Fetch using the CRUD get method which handles string ID
            sub = crud_submission.submission.get(db, id_=submission_id)
            if not sub:
                print(f"[Worker {worker_id}] Submission {submission_id[:8]} not found in DB.")
                return

            terminal_statuses = { s.value for s in SubmissionStatus if s not in [SubmissionStatus.PENDING, SubmissionStatus.RUNNING] }
            if sub.status in terminal_statuses:
                 print(f"[Worker {worker_id}] Submission {submission_id[:8]} already has terminal status '{sub.status}'. Skipping.")
                 return

            # Mark RUNNING (commit within this worker's session)
            sub.status = SubmissionStatus.RUNNING.value
            db.add(sub)
            db.commit()
            db.refresh(sub)
            print(f"[Worker {worker_id}] Marked {submission_id[:8]} as RUNNING.")

            # Get Problem
            problem = get_problem_by_id(sub.contest_id, sub.problem_id)
            if not problem:
                print(f"[Worker {worker_id}] Problem not found for {submission_id[:8]}. Marking INTERNAL_ERROR.")
                err = TestCaseResult(test_case_name="Setup", status=SubmissionStatus.INTERNAL_ERROR, stderr="Problem definition not found")
                crud_submission.submission.update_submission_results(db, db_obj=sub, status=SubmissionStatus.INTERNAL_ERROR.value, results=[err])
                return

            # Run Test Cases
            final_results: List[TestCaseResult] = []
            overall_status = SubmissionStatus.ACCEPTED

            print(f"[Worker {worker_id}] Running {len(problem.test_cases)} test cases for {submission_id[:8]}...")
            for i, tc in enumerate(problem.test_cases):
                print(f"[Worker {worker_id}] Running TC {i+1}/{len(problem.test_cases)} ('{tc.name}') for {submission_id[:8]}...")
                try:
                    # Convert string ID back to UUID for run_code_in_sandbox
                    res = await run_code_in_sandbox(
                        submission_id=uuid.UUID(submission_id),
                        code=sub.code,
                        problem=problem,
                        test_case=tc,
                        language=sub.language
                    )
                    print(f"[Worker {worker_id}] TC {i+1} Result for {submission_id[:8]}: {res.status.name}")
                except Exception as e:
                    print(f"[Worker {worker_id}] Executor error on TC {i+1} for {submission_id[:8]}: {e}")
                    traceback.print_exc()
                    res = TestCaseResult(test_case_name=tc.name, status=SubmissionStatus.INTERNAL_ERROR, stderr=f"Executor error: {type(e).__name__}: {e}")
                final_results.append(res)

                if res.status != SubmissionStatus.ACCEPTED and overall_status == SubmissionStatus.ACCEPTED:
                    overall_status = res.status
                    # break # Optional: stop on first non-AC

            print(f"[Worker {worker_id}] Finished all TCs for {submission_id[:8]}. Overall Status: {overall_status.name}. Persisting results...")

            # Persist final results using CRUD update (handles commit)
            crud_submission.submission.update_submission_results(
                db,
                db_obj=sub,
                status=overall_status.value, # Pass the final status string
                results=final_results
            )
            print(f"[Worker {worker_id}] Results persisted for {submission_id[:8]}.")

        except Exception as e:
            print(f"[Worker {worker_id}] Unexpected error in _process_submission for {submission_id[:8]}: {type(e).__name__}: {e}")
            traceback.print_exc()
            await self._mark_submission_internal_error(submission_id, f"Processing failed: {e}")
        finally:
            if db:
                db.close()

    async def _mark_submission_internal_error(self, submission_id: str, error_message: str):
        """Attempts to mark a submission as Internal Error in the DB."""
        db: Optional[Session] = None
        try:
            db = SessionLocal()
            sub = crud_submission.submission.get(db, id_=submission_id)
            if sub and sub.status != SubmissionStatus.INTERNAL_ERROR.value:
                err = TestCaseResult(test_case_name="Processing Failure", status=SubmissionStatus.INTERNAL_ERROR, stderr=f"Queue worker error: {error_message[:500]}")
                crud_submission.submission.update_submission_results(db, db_obj=sub, status=SubmissionStatus.INTERNAL_ERROR.value, results=[err])
                print(f"[Queue Fallback] Marked {submission_id[:8]} as INTERNAL_ERROR due to: {error_message[:100]}...")
        except Exception as db_err:
            print(f"[Queue Fallback] FAILED to mark {submission_id[:8]} as INTERNAL_ERROR in DB: {db_err}")
        finally:
            if db:
                db.close()

# --- Instantiate the CORRECT processing queue on import ---
QUEUE_WORKER_COUNT = (os.cpu_count() or 1) # Adjust as needed
submission_processing_queue = SubmissionProcessingQueue(worker_count=QUEUE_WORKER_COUNT)
