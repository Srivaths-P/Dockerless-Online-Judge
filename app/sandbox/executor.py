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
              "-p", "MemoryAccounting=yes",
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
    execution_time_ns = 0
    try:
        stdin_file = open(stdin_path, 'rb') if stdin_path else subprocess.DEVNULL
        stdout_file = open(stdout_path, 'wb')
        stderr_file = open(stderr_path, 'wb')

        start_time_ns = time.perf_counter_ns()
        proc = subprocess.run(
            full_cmd,
            stdin=stdin_file,
            stdout=stdout_file,
            stderr=stderr_file
        )
        end_time_ns = time.perf_counter_ns()
        execution_time_ns = end_time_ns - start_time_ns
        exit_code = proc.returncode

    finally:
        if stdin_file and stdin_file != subprocess.DEVNULL:
            stdin_file.close()
        if stdout_file:
            stdout_file.close()
        if stderr_file:
            stderr_file.close()

    peak_rss_kb = -1
    try:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        peak_rss_kb = usage.ru_maxrss
    except Exception:
        peak_rss_kb = -1

    show = subprocess.run(
        ["systemctl", "show", "-p", "Result", "--value", f"{unit}.scope"],
        capture_output=True, text=True, check=False
    )
    systemd_result = show.stdout.strip() if show.returncode == 0 else "unknown"

    mem_show = subprocess.run(
        ["systemctl", "show", "-p", "MemoryPeak", "--value", f"{unit}.scope"],
        capture_output=True, text=True, check=False
    )
    systemd_mem_bytes = -1
    if mem_show.returncode == 0 and mem_show.stdout.strip().isdigit():
        systemd_mem_bytes = int(mem_show.stdout.strip())

    subprocess.run(
        ["systemctl", "reset-failed", f"{unit}.scope"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )
    subprocess.run(
        ["systemctl", "stop", f"{unit}.scope"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )

    final_mem_kb = int(systemd_mem_bytes / 1024) if systemd_mem_bytes > 0 else peak_rss_kb

    return {
        "systemd": systemd_result,
        "exit": exit_code,
        "mem_kb": final_mem_kb,
        "time_ns": execution_time_ns
    }


def _diff_files(out_path: str, exp_path: str) -> int:
    if not os.path.exists(out_path):
        open(out_path, 'w').close()
    if not os.path.exists(exp_path):
        open(exp_path, 'w').close()
    cp = subprocess.run(
        ["diff", "-Z", "--strip-trailing-cr", "-q", out_path, exp_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True
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

        in_f_for_bwrap = None
        if test_case.input_content is not None:
            with open(in_f, 'w', encoding='utf-8') as f:
                f.write(test_case.input_content)
            in_f_for_bwrap = in_f

        if test_case.output_content is not None:
            with open(exp_f, 'w', encoding='utf-8') as f:
                f.write(test_case.output_content)
        elif not os.path.exists(exp_f):
            open(exp_f, 'w').close()

        stderr_msg = None
        compilation_mem_kb = None

        if cfg["compile"]:
            unit_c = f"compile-{submission_id.hex[:8]}-{uuid.uuid4().hex[:4]}"
            compile_out_f = os.path.join(results_dir, "compile.out")
            compile_err_f = os.path.join(results_dir, "compile.err")
            bwrap_args_c = [
                               "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                               "--ro-bind", "/lib64", "/lib64", "--bind", td, "/sandbox",
                               "--proc", "/proc", "--dev", "/dev", "--chdir", "/sandbox",
                               "--unshare-pid", "--unshare-net",
                           ] + cfg["compile"]

            cres = await asyncio.get_running_loop().run_in_executor(
                blocking_executor,
                _systemd_bwrap_run,
                unit_c, 30, 512,
                bwrap_args_c,
                None, compile_out_f, compile_err_f
            )

            compilation_mem_kb = cres.get("mem_kb", None)

            if cres["systemd"] != "success" or cres["exit"] != 0:
                if os.path.exists(compile_err_f):
                    try:
                        with open(compile_err_f, 'r', encoding='utf-8', errors='ignore') as ef:
                            stderr_msg = ef.read(4096).strip()
                    except Exception:
                        stderr_msg = "Failed to read compiler error output."
                else:
                    stderr_msg = "Compilation failed (no error output file found)."

                if cres["systemd"] == "timeout":
                    stderr_msg = f"Compilation Timed Out ({stderr_msg})".strip()
                elif cres["systemd"] in ("oom", "memory", "oom-kill"):
                    stderr_msg = f"Compilation Memory Limit Exceeded ({stderr_msg})".strip()

                return TestCaseResult(
                    test_case_name=test_case.name,
                    status=SubmissionStatus.COMPILATION_ERROR,
                    stderr=stderr_msg,
                    execution_time_ms=0.0,
                    memory_used_kb=compilation_mem_kb
                )

        unit_e = f"exec-{submission_id.hex[:8]}-{uuid.uuid4().hex[:4]}"
        bwrap_args_e = [
                           "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                           "--ro-bind", "/lib64", "/lib64", "--bind", td, "/sandbox",
                           "--proc", "/proc", "--dev", "/dev", "--chdir", "/sandbox",
                           "--unshare-pid", "--unshare-net",
                       ] + cfg["run"]

        eres = await asyncio.get_running_loop().run_in_executor(
            blocking_executor, _systemd_bwrap_run, unit_e,
            problem.time_limit_sec, problem.memory_limit_mb,
            bwrap_args_e, in_f_for_bwrap, out_f, err_f
        )
        exec_ns = eres.get("time_ns", 0)
        sysd = eres["systemd"]
        ret = eres["exit"]
        mem_kb = eres.get("mem_kb", None)
        exec_ms = round(exec_ns / 1_000_000, 2)

        status = SubmissionStatus.INTERNAL_ERROR

        if sysd == "timeout":
            status = SubmissionStatus.TIME_LIMIT_EXCEEDED
            exec_ms = float(problem.time_limit_sec * 1000)
        elif sysd in ("oom", "memory", "oom-kill"):
            status = SubmissionStatus.MEMORY_LIMIT_EXCEEDED
        elif sysd == "success":
            if ret != 0:
                status = SubmissionStatus.RUNTIME_ERROR
            else:
                diffc = await asyncio.get_running_loop().run_in_executor(
                    blocking_executor,
                    _diff_files,
                    out_f, exp_f
                )
                status = SubmissionStatus.ACCEPTED if diffc == 0 else SubmissionStatus.WRONG_ANSWER
        elif sysd == "failed":
            status = SubmissionStatus.RUNTIME_ERROR if ret != 0 else SubmissionStatus.INTERNAL_ERROR
        else:
            status = SubmissionStatus.INTERNAL_ERROR
            stderr_msg = f"Execution failed (systemd: {sysd}, exit: {ret})"

        if os.path.exists(err_f):
            try:
                with open(err_f, 'r', encoding='utf-8', errors='ignore') as ef:
                    stderr_content = ef.read(4096).strip()
                if stderr_content:
                    if stderr_msg:
                        stderr_msg = f"{stderr_msg}\n---\n{stderr_content}"
                    else:
                        stderr_msg = stderr_content
            except Exception:
                if stderr_msg:
                    stderr_msg = f"{stderr_msg}\n---\n(Failed to read stderr)"
                else:
                    stderr_msg = "(Failed to read stderr)"

        stdout_content = None
        if status == SubmissionStatus.WRONG_ANSWER and os.path.exists(out_f):
            try:
                with open(out_f, 'r', encoding='utf-8', errors='ignore') as of:
                    stdout_content = of.read(4096).strip()
            except Exception:
                stdout_content = "(Failed to read stdout)"

        return TestCaseResult(
            test_case_name=test_case.name, status=status, stdout=stdout_content, stderr=stderr_msg,
            execution_time_ms=exec_ms, memory_used_kb=mem_kb
        )
    except Exception as e:
        traceback.print_exc()
        return TestCaseResult(
            test_case_name=test_case.name, status=SubmissionStatus.INTERNAL_ERROR,
            stderr=f"Sandbox setup/internal error: {type(e).__name__}: {e}",
            execution_time_ms=0.0, memory_used_kb=None
        )
    finally:
        shutil.rmtree(td, ignore_errors=True)


async def run_generator_in_sandbox(
        problem_for_generator: Problem,
        generator_language: str = "python"
) -> Dict[str, Any]:
    lang = generator_language.lower()
    cfg = LANGUAGE_CONFIG.get(lang)
    if not cfg:
        return {"input": None, "output": None,
                "error": f"Unsupported generator language: {generator_language}",
                "status": "error"}

    if not problem_for_generator.generator_code:
        return {"input": None, "output": None,
                "error": "Generator code not found in problem object.",
                "status": "error"}

    generator_code = problem_for_generator.generator_code

    td_prefix = f"generator_{uuid.uuid4().hex[:8]}_"
    td = tempfile.mkdtemp(prefix=td_prefix)

    try:
        code_f = os.path.join(td, "user_code" + cfg["ext"])
        results_dir = os.path.join(td, "results")
        os.makedirs(results_dir, exist_ok=True)
        out_f = os.path.join(results_dir, "generator.stdout")
        err_f = os.path.join(results_dir, "generator.stderr")

        with open(code_f, 'w', encoding='utf-8') as f:
            f.write(generator_code)

        if cfg["compile"]:
            return {"input": None, "output": None,
                    "error": "Generator compilation not supported yet.",
                    "status": "error"}

        unit_g = f"gen-{uuid.uuid4().hex[:8]}"
        bwrap_args_g = [
                           "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                           "--ro-bind", "/lib64", "/lib64", "--bind", td, "/sandbox",
                           "--proc", "/proc", "--dev", "/dev", "--chdir", "/sandbox",
                           "--unshare-pid", "--unshare-net",
                       ] + cfg["run"]

        g_tlim = problem_for_generator.generator_time_limit_sec
        g_mlim = problem_for_generator.generator_memory_limit_mb

        g_tlim = max(1, g_tlim)

        gres = await asyncio.get_running_loop().run_in_executor(
            blocking_executor, _systemd_bwrap_run, unit_g,
            g_tlim, g_mlim,
            bwrap_args_g, None, out_f, err_f
        )

        sysd = gres["systemd"]
        ret = gres["exit"]
        mem_kb = gres.get("mem_kb", None)
        exec_ms = round(gres.get("time_ns", 0) / 1_000_000, 2)

        input_content = None
        output_content = None
        error_content = None

        if os.path.exists(out_f):
            try:
                with open(out_f, 'r', encoding='utf-8', errors='ignore') as f:
                    input_content = f.read(8192).strip()
            except Exception as e:
                input_content = f"(Failed to read generator stdout: {e})"

        if os.path.exists(err_f):
            try:
                with open(err_f, 'r', encoding='utf-8', errors='ignore') as f:
                    output_content = f.read(8192).strip()
            except Exception as e:
                output_content = f"(Failed to read generator stderr: {e})"

        if sysd != "success" or ret != 0:
            status_reason = f"Systemd: {sysd}, Exit Code: {ret}, Time: {exec_ms}ms, Mem: {mem_kb}KB"
            if sysd == "timeout":
                error_content = f"Generator Timed Out ({g_tlim}s). {status_reason}"
            elif sysd in ("oom", "memory", "oom-kill"):
                error_content = f"Generator Memory Limit Exceeded ({g_mlim}MB). {status_reason}"
            elif sysd == "failed" and ret != 0:
                error_content = f"Generator execution command failed. {status_reason}"
            elif ret != 0:
                error_content = f"Generator script exited with error code {ret}. {status_reason}"
                if output_content:
                    error_content += f"\n---\nGenerator Script Error Output:\n{output_content}"
            else:
                error_content = f"Generator execution failed unexpectedly. {status_reason}"

            input_content = None
            output_content = None

        return {
            "input": input_content,
            "output": output_content,
            "error": error_content,
            "execution_time_ms": exec_ms,
            "memory_used_kb": mem_kb,
            "status": "success" if error_content is None else "error"
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "input": None, "output": None,
            "error": f"Generator sandbox critical error: {type(e).__name__}: {e}",
            "execution_time_ms": 0.0, "memory_used_kb": None, "status": "internal_error"
        }

    finally:
        shutil.rmtree(td, ignore_errors=True)


class SubmissionProcessingQueue:
    def __init__(self, worker_count: int):
        self._queue = asyncio.Queue()
        self._worker_count = worker_count
        self._workers: List[asyncio.Task] = []

    async def start_workers(self):
        if self._workers:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._workers = [
            loop.create_task(self._worker(worker_id=i))
            for i in range(self._worker_count)
        ]

    async def stop_workers(self):
        if not self._workers:
            return
        for _ in self._workers:
            await self._queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def enqueue(self, submission_id: str):
        await self._queue.put(submission_id)

    async def _worker(self, worker_id: int):
        while True:
            submission_id = await self._queue.get()
            if submission_id is None:
                self._queue.task_done()
                break
            try:
                await self._process_submission(submission_id, worker_id)
            except Exception as e:
                traceback.print_exc()
                await self._handle_error(submission_id, f"Worker processing failed: {e}")
            self._queue.task_done()

    async def _process_submission(self, submission_id: str, worker_id: int):
        db: Optional[Session] = None
        try:
            db = SessionLocal()
            sub = crud_submission.submission.get(db, id_=submission_id)
            if not sub:
                return

            terminal_statuses = {s.value for s in SubmissionStatus if
                                 s not in [SubmissionStatus.PENDING, SubmissionStatus.RUNNING]}
            if sub.status in terminal_statuses:
                return

            sub.status = SubmissionStatus.RUNNING.value
            db.add(sub)
            db.commit()
            db.refresh(sub)

            problem = get_problem_by_id(sub.contest_id, sub.problem_id)
            if not problem:
                err = TestCaseResult(test_case_name="Setup", status=SubmissionStatus.INTERNAL_ERROR,
                                     stderr="Problem definition not found")
                crud_submission.submission.update_submission_results(db, db_obj=sub,
                                                                     status=SubmissionStatus.INTERNAL_ERROR.value,
                                                                     results=[err])
                return

            final_results: List[TestCaseResult] = []
            overall_status = SubmissionStatus.ACCEPTED

            for i, tc in enumerate(problem.test_cases):
                try:
                    res = await run_code_in_sandbox(
                        submission_id=uuid.UUID(submission_id),
                        code=sub.code,
                        problem=problem,
                        test_case=tc,
                        language=sub.language
                    )
                except Exception as e:
                    traceback.print_exc()
                    res = TestCaseResult(test_case_name=tc.name, status=SubmissionStatus.INTERNAL_ERROR,
                                         stderr=f"Executor error: {type(e).__name__}: {e}")
                final_results.append(res)
                if res.status != SubmissionStatus.ACCEPTED:
                    if overall_status == SubmissionStatus.ACCEPTED:
                        overall_status = res.status
                    break

            crud_submission.submission.update_submission_results(
                db,
                db_obj=sub,
                status=overall_status.value,
                results=final_results
            )
        except Exception as e:
            if db:
                db.rollback()
            raise
        finally:
            if db:
                db.close()

    async def _handle_error(self, submission_id: str, error_message: str):
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
        except Exception as db_err:
            if db: db.rollback()
        finally:
            if db:
                db.close()


QUEUE_WORKER_COUNT = (os.cpu_count() or 1)
submission_processing_queue = SubmissionProcessingQueue(worker_count=QUEUE_WORKER_COUNT)
