
import asyncio
import os
import resource
import shutil
import subprocess
import tempfile
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, List
import json

from sqlalchemy.orm import Session

from app.crud import crud_submission
from app.db.session import SessionLocal
from app.schemas.problem import Problem, TestCase
from app.schemas.submission import SubmissionStatus, TestCaseResult
from app.services.contest_service import get_problem_by_id

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

MAX_THREADS = (os.cpu_count() or 2) * 2
blocking_executor = ThreadPoolExecutor(max_workers=MAX_THREADS)


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
        stdin_path: Optional[str],
        stdout_path: str,
        stderr_path: str
) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(stdout_path), exist_ok=True)
    os.makedirs(os.path.dirname(stderr_path), exist_ok=True)

    full_cmd = _make_systemd_bwrap_cmd(unit, tlim, mlim, bwrap_args)

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
        )
        exit_code = proc.returncode

    finally:
        if stdin_file and stdin_file != subprocess.DEVNULL:
            stdin_file.close()
        if stdout_file:
            stdout_file.close()
        if stderr_file:
            stderr_file.close()

    try:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        peak_rss_kb = usage.ru_maxrss
    except Exception:
        peak_rss_kb = -1

    show = subprocess.run(
        ["systemctl", "show", "-p", "Result", f"{unit}.scope"],
        capture_output=True, text=True, check=False
    )
    _, _, raw = show.stdout.partition("=")
    systemd_result = raw.strip() if show.returncode == 0 else "unknown"

    subprocess.run(
        ["systemctl", "reset-failed", f"{unit}.scope"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )
    return {
        "systemd": systemd_result,
        "exit": exit_code,
        "mem_kb": peak_rss_kb
    }


def _diff_files(out_path: str, exp_path: str) -> int:
    if not os.path.exists(out_path):
        with open(out_path, 'w') as f: pass
    if not os.path.exists(exp_path):
        with open(exp_path, 'w') as f: pass

    cp = subprocess.run(
        ["diff", "-Z", "--strip-trailing-cr", "-q", out_path, exp_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return cp.returncode


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

    td_prefix = f"judge_{submission_id.hex[:8]}_{test_case.name.replace(' ', '_')}_"
    td = tempfile.mkdtemp(prefix=td_prefix)

    try:
        code_f = os.path.join(td, "user_code" + cfg["ext"])
        in_f = os.path.join(td, "input.txt")
        results_dir = os.path.join(td, "results")
        os.makedirs(results_dir, exist_ok=True)
        out_f = os.path.join(results_dir, f"{submission_id.hex}.out")
        err_f = os.path.join(results_dir, f"{submission_id.hex}.err")
        exp_f = os.path.join(results_dir, "expected.txt")

        with open(code_f, 'w', encoding='utf-8') as f:
            f.write(code)
        with open(in_f, 'w', encoding='utf-8') as f:
            if test_case.input_content:
                f.write(test_case.input_content)
        with open(exp_f, 'w', encoding='utf-8') as f:
            if test_case.output_content:
                f.write(test_case.output_content)

        status = SubmissionStatus.INTERNAL_ERROR
        stderr_msg = None
        exec_ms = 0.0
        mem_kb = None

        if cfg["compile"]:
            unit_c = f"compile-{submission_id.hex[:8]}-{uuid.uuid4().hex[:4]}"
            compile_out_f = os.path.join(results_dir, "compile.out")
            compile_err_f = os.path.join(results_dir, "compile.err")
            bwrap_args_c = [
                               "--ro-bind", "/usr", "/usr",
                               "--ro-bind", "/lib", "/lib",
                               "--ro-bind", "/lib64", "/lib64",
                               "--bind", td, "/sandbox",
                               "--proc", "/proc",
                               "--dev", "/dev",
                               "--chdir", "/sandbox",
                               "--unshare-pid",
                               "--unshare-net",
                           ] + cfg["compile"]

            cres = await asyncio.get_running_loop().run_in_executor(
                blocking_executor,
                _systemd_bwrap_run,
                unit_c, 30, 512,
                bwrap_args_c,
                None, compile_out_f, compile_err_f
            )

            mem_kb = cres.get("mem_kb", None)

            if cres["systemd"] != "success" or cres["exit"] != 0:
                if os.path.exists(compile_err_f):
                    try:
                        with open(compile_err_f, 'r', encoding='utf-8', errors='ignore') as ef:
                            stderr_msg = ef.read(2048).strip()
                    except Exception:
                        stderr_msg = "Failed to read compiler error output."
                else:
                    stderr_msg = "Compilation failed (no error output)."

                if cres["systemd"] == "timeout":
                    stderr_msg = f"Compilation Timed Out ({stderr_msg})"
                elif cres["systemd"] in ("oom", "memory", "oom-kill"):
                    stderr_msg = f"Compilation Memory Limit Exceeded ({stderr_msg})"

                return TestCaseResult(
                    test_case_name=test_case.name,
                    status=SubmissionStatus.COMPILATION_ERROR,
                    stderr=stderr_msg,
                    execution_time_ms=0.0,
                    memory_used_kb=mem_kb
                )

        unit_e = f"exec-{submission_id.hex[:8]}-{uuid.uuid4().hex[:4]}"
        bwrap_args_e = [
                           "--ro-bind", "/usr", "/usr",
                           "--ro-bind", "/lib", "/lib",
                           "--ro-bind", "/lib64", "/lib64",
                           "--bind", td, "/sandbox",
                           "--proc", "/proc",
                           "--dev", "/dev",
                           "--chdir", "/sandbox",
                           "--unshare-pid",
                           "--unshare-net",
                       ] + cfg["run"]

        t0 = time.perf_counter_ns()
        eres = await asyncio.get_running_loop().run_in_executor(
            blocking_executor,
            _systemd_bwrap_run,
            unit_e,
            problem.time_limit_sec + 1,
            problem.memory_limit_mb,
            bwrap_args_e,
            in_f, out_f, err_f
        )
        exec_ns = time.perf_counter_ns() - t0

        sysd = eres["systemd"]
        ret = eres["exit"]
        mem_kb = eres.get("mem_kb", None)
        exec_ms = round(exec_ns / 1_000_000, 2)

        diffc = -1
        if sysd == "success" and ret == 0:
            diffc = await asyncio.get_running_loop().run_in_executor(
                blocking_executor,
                _diff_files,
                out_f, exp_f
            )

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
            status = SubmissionStatus.RUNTIME_ERROR
        else:
            status = SubmissionStatus.INTERNAL_ERROR
            stderr_msg = f"Execution failed (systemd: {sysd}, exit: {ret})"

        if status != SubmissionStatus.ACCEPTED:
            if os.path.exists(err_f):
                try:
                    with open(err_f, 'r', encoding='utf-8', errors='ignore') as ef:
                        stderr_content = ef.read(2048).strip()
                        stderr_msg = f"{stderr_msg}\n{stderr_content}".strip() if stderr_msg else stderr_content
                except Exception:
                    stderr_msg = f"{stderr_msg}\n(Failed to read stderr)".strip() if stderr_msg else "(Failed to read stderr)"

        if status == SubmissionStatus.TIME_LIMIT_EXCEEDED:
            exec_ms = float(problem.time_limit_sec * 1000)

        return TestCaseResult(
            test_case_name=test_case.name,
            status=status,
            stdout=None,
            stderr=stderr_msg,
            execution_time_ms=exec_ms,
            memory_used_kb=mem_kb
        )

    except Exception as e:
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
        shutil.rmtree(td, ignore_errors=True)

class SubmissionProcessingQueue:
    def __init__(self, worker_count: int):
        self._queue = asyncio.Queue()
        self._worker_count = worker_count
        self._workers: List[asyncio.Task] = []
        print(f"[Queue] Initialized with capacity for {worker_count} workers.")

    async def start_workers(self):
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
        if not self._workers:
            print("[Queue] No workers to stop.")
            return
        print("[Queue] Stopping workers...")
        for _ in self._workers:
            await self._queue.put(None)
        print("[Queue] Waiting for workers to finish...")
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        print("[Queue] All workers stopped.")
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break
        print("[Queue] Shutdown complete.")

    async def enqueue(self, submission_id: str):
        if not self._workers:
            print("[Queue] WARNING: Enqueuing submission, but workers are not running!")
        await self._queue.put(submission_id)
        print(f"[Queue] Enqueued submission {submission_id[:8]}... Queue size: {self._queue.qsize()}")

    async def _worker(self, worker_id: int):
        print(f"[Worker {worker_id}] Starting...")
        while True:
            submission_id = await self._queue.get()
            if submission_id is None:
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
            print(
                f"[Worker {worker_id}] Finished submission {submission_id[:8]} in {end_time - start_time:.2f}s. Queue size: {self._queue.qsize()}")
            self._queue.task_done()
        print(f"[Worker {worker_id}] Stopped.")

    async def _process_submission(self, submission_id: str, worker_id: int):
        db: Optional[Session] = None
        sub = None
        try:
            db = SessionLocal()
            sub = crud_submission.submission.get(db, id_=submission_id)
            if not sub:
                print(f"[Worker {worker_id}] Submission {submission_id[:8]} not found in DB.")
                return

            terminal_statuses = {s.value for s in SubmissionStatus if
                                 s not in [SubmissionStatus.PENDING, SubmissionStatus.RUNNING]}
            if sub.status in terminal_statuses:
                print(
                    f"[Worker {worker_id}] Submission {submission_id[:8]} already has terminal status '{sub.status}'. Skipping.")
                return

            sub.status = SubmissionStatus.RUNNING.value
            db.add(sub)
            db.commit()
            db.refresh(sub)
            print(f"[Worker {worker_id}] Marked {submission_id[:8]} as RUNNING.")

            problem = get_problem_by_id(sub.contest_id, sub.problem_id)
            if not problem:
                print(f"[Worker {worker_id}] Problem not found for {submission_id[:8]}. Marking INTERNAL_ERROR.")
                err = TestCaseResult(test_case_name="Setup", status=SubmissionStatus.INTERNAL_ERROR,
                                     stderr="Problem definition not found")
                crud_submission.submission.update_submission_results(db, db_obj=sub,
                                                                     status=SubmissionStatus.INTERNAL_ERROR.value,
                                                                     results=[err])
                return

            final_results: List[TestCaseResult] = []
            overall_status = SubmissionStatus.ACCEPTED

            print(f"[Worker {worker_id}] Running {len(problem.test_cases)} test cases for {submission_id[:8]}...")
            for i, tc in enumerate(problem.test_cases):
                print(
                    f"[Worker {worker_id}] Running TC {i + 1}/{len(problem.test_cases)} ('{tc.name}') for {submission_id[:8]}...")
                try:
                    res = await run_code_in_sandbox(
                        submission_id=uuid.UUID(submission_id),
                        code=sub.code,
                        problem=problem,
                        test_case=tc,
                        language=sub.language
                    )
                    print(f"[Worker {worker_id}] TC {i + 1} Result for {submission_id[:8]}: {res.status.name}")
                except Exception as e:
                    print(f"[Worker {worker_id}] Executor error on TC {i + 1} for {submission_id[:8]}: {e}")
                    traceback.print_exc()
                    res = TestCaseResult(test_case_name=tc.name, status=SubmissionStatus.INTERNAL_ERROR,
                                         stderr=f"Executor error: {type(e).__name__}: {e}")
                final_results.append(res)
                if res.status != SubmissionStatus.ACCEPTED and overall_status == SubmissionStatus.ACCEPTED:
                    overall_status = res.status

            print(
                f"[Worker {worker_id}] Finished all TCs for {submission_id[:8]}. Overall Status: {overall_status.name}. Persisting results...")
            crud_submission.submission.update_submission_results(
                db,
                db_obj=sub,
                status=overall_status.value,
                results=final_results
            )
            print(f"[Worker {worker_id}] Results persisted for {submission_id[:8]}.")
        except Exception as e:
            print(
                f"[Worker {worker_id}] Unexpected error in _process_submission for {submission_id[:8]}: {type(e).__name__}: {e}")
            traceback.print_exc()
            await self._mark_submission_internal_error(submission_id, f"Processing failed: {e}")
        finally:
            if db:
                db.close()

    async def _mark_submission_internal_error(self, submission_id: str, error_message: str):
        db: Optional[Session] = None
        try:
            db = SessionLocal()
            sub = crud_submission.submission.get(db, id_=submission_id)
            if sub and sub.status != SubmissionStatus.INTERNAL_ERROR.value:
                err = TestCaseResult(test_case_name="Processing Failure", status=SubmissionStatus.INTERNAL_ERROR,
                                     stderr=f"Queue worker error: {error_message[:500]}")
                crud_submission.submission.update_submission_results(db, db_obj=sub,
                                                                     status=SubmissionStatus.INTERNAL_ERROR.value,
                                                                     results=[err])
                print(f"[Queue Fallback] Marked {submission_id[:8]} as INTERNAL_ERROR due to: {error_message[:100]}...")
        except Exception as db_err:
            print(f"[Queue Fallback] FAILED to mark {submission_id[:8]} as INTERNAL_ERROR in DB: {db_err}")
        finally:
            if db:
                db.close()

QUEUE_WORKER_COUNT = (os.cpu_count() or 1)
submission_processing_queue = SubmissionProcessingQueue(worker_count=QUEUE_WORKER_COUNT)
