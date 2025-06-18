import asyncio
import os
import shutil
import subprocess
import tempfile
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

WRAPPER_SCRIPT = """
import os
import resource
import sys
import time

command = sys.argv[1:]

stdin_path = '/sandbox/input.txt'
stdout_path = '/sandbox/results/user.stdout'
stderr_path = '/sandbox/results/user.stderr'
res_log_path = '/sandbox/res.log'

if os.path.exists(stdin_path):
    stdin_fd = os.open(stdin_path, os.O_RDONLY)
else:
    stdin_fd = os.open(os.devnull, os.O_RDONLY)

stdout_fd = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
stderr_fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)

pid = os.fork()

if pid == 0:
    try:
        os.dup2(stdin_fd, sys.stdin.fileno())
        os.dup2(stdout_fd, sys.stdout.fileno())
        os.dup2(stderr_fd, sys.stderr.fileno())
        os.execv(command[0], command)
    except Exception as e:
        os.write(stderr_fd, f"Wrapper execv error: {e}".encode())
        os._exit(127)
else:
    start_time = time.perf_counter()
    _pid, status, rusage = os.wait4(pid, 0)
    end_time = time.perf_counter()

    wall_time_s = end_time - start_time
    mem_kb = rusage.ru_maxrss
    exit_code = os.waitstatus_to_exitcode(status)

    with open(res_log_path, 'w') as f:
        f.write(f"EXIT_CODE:{exit_code}\\n")
        f.write(f"WALL_S:{wall_time_s:.4f}\\n")
        f.write(f"MEM_KB:{mem_kb}\\n")

    os.close(stdin_fd)
    os.close(stdout_fd)
    os.close(stderr_fd)
"""

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
              "systemd-run", "--quiet", "--scope", "--user",
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
) -> Dict[str, Any]:
    full_cmd = _make_systemd_bwrap_cmd(unit, tlim, mlim, bwrap_args)
    subprocess.run(full_cmd, check=False)

    systemd_result_str = "unknown"
    try:
        scope_unit_name = f"{unit}.scope"
        show_cmd = ["systemctl", "show", "--user", scope_unit_name, "-p", "Result", "--value"]
        res = subprocess.run(show_cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            systemd_result_str = res.stdout.strip()
    except Exception as e:
        print(f"Failed to get systemd result for {unit}: {e}")

    subprocess.run(["systemctl", "--user", "reset-failed", f"{unit}.scope"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    subprocess.run(["systemctl", "--user", "stop", f"{unit}.scope"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    return {"systemd_result": systemd_result_str}


def _diff_files(out_path: str, exp_path: str) -> int:
    if not os.path.exists(out_path): open(out_path, 'w').close()
    if not os.path.exists(exp_path): open(exp_path, 'w').close()
    return subprocess.run(["diff", "-Z", "--strip-trailing-cr", "-q", out_path, exp_path],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


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
        return TestCaseResult(test_case_name=test_case.name, status=SubmissionStatus.INTERNAL_ERROR,
                              stderr=f"Unsupported language: {language}")

    td = tempfile.mkdtemp(prefix=f"judge_{submission_id.hex[:8]}_")

    try:
        results_dir = os.path.join(td, "results")
        os.makedirs(results_dir, exist_ok=True)

        out_f = os.path.join(results_dir, "user.stdout")
        err_f = os.path.join(results_dir, "user.stderr")
        res_log_f = os.path.join(td, "res.log")
        in_f = os.path.join(td, "input.txt")
        exp_f = os.path.join(td, "expected.txt")
        wrapper_f = os.path.join(td, "wrapper.py")

        with open(os.path.join(td, "user_code" + cfg["ext"]), 'w') as f:
            f.write(code)
        with open(wrapper_f, 'w') as f:
            f.write(WRAPPER_SCRIPT)
        if test_case.input_content is not None:
            with open(in_f, 'w') as f: f.write(test_case.input_content)
        with open(exp_f, 'w') as f:
            f.write(test_case.output_content or "")

        if cfg["compile"]:
            unit_c = f"compile-{submission_id.hex[:8]}-{uuid.uuid4().hex[:4]}"
            bwrap_args_c = ["--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                            "--ro-bind", "/lib64", "/lib64", "--bind", td, "/sandbox",
                            "--proc", "/proc", "--dev", "/dev", "--chdir", "/sandbox",
                            "--unshare-pid", "--unshare-net"] + cfg["compile"]

            cres = await asyncio.get_running_loop().run_in_executor(
                blocking_executor, _systemd_bwrap_run, unit_c, 30, 512, bwrap_args_c
            )

            compile_err_f = os.path.join(results_dir, "compile.stderr")
            compile_log_f = os.path.join(td, "compile_res.log")

            compile_wrapper_script = WRAPPER_SCRIPT.replace(
                "'/sandbox/results/user.stdout'", f"'/dev/null'"
            ).replace(
                "'/sandbox/results/user.stderr'", f"'{os.path.join('/sandbox/results', 'compile.stderr')}'"
            ).replace(
                "'/sandbox/res.log'", f"'/sandbox/compile_res.log'"
            )
            with open(wrapper_f, 'w') as f:
                f.write(compile_wrapper_script)

            bwrap_args_c_wrapped = ["--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                                    "--ro-bind", "/lib64", "/lib64", "--bind", td, "/sandbox",
                                    "--proc", "/proc", "--dev", "/dev", "--chdir", "/sandbox",
                                    "--unshare-pid", "--unshare-net",
                                    PYTHON3, "/sandbox/wrapper.py"] + cfg["compile"]

            cres = await asyncio.get_running_loop().run_in_executor(
                blocking_executor, _systemd_bwrap_run, unit_c, 30, 512, bwrap_args_c_wrapped
            )

            compile_exit_code = -1
            try:
                with open(compile_log_f, 'r') as f:
                    for line in f:
                        if line.startswith("EXIT_CODE:"):
                            compile_exit_code = int(line.strip().split(':')[1])
            except (IOError, IndexError, ValueError):
                pass

            if cres.get("systemd_result") != "success" or compile_exit_code != 0:
                compile_stderr = ""
                if os.path.exists(compile_err_f):
                    with open(compile_err_f, 'r', errors='ignore') as f:
                        compile_stderr = f.read(4096).strip()
                if cres.get("systemd_result") == "timeout":
                    compile_stderr = "Compilation Timed Out.\n" + compile_stderr
                elif cres.get("systemd_result") == "oom-kill":
                    compile_stderr = "Compilation Memory Limit Exceeded.\n" + compile_stderr

                return TestCaseResult(test_case_name=test_case.name, status=SubmissionStatus.COMPILATION_ERROR,
                                      stderr=compile_stderr or "Compilation failed.")

            with open(wrapper_f, 'w') as f:
                f.write(WRAPPER_SCRIPT)

            executable_path = os.path.join(td, "user_exec")
            if os.path.exists(executable_path):
                os.chmod(executable_path, 0o755)
            else:
                return TestCaseResult(test_case_name=test_case.name, status=SubmissionStatus.INTERNAL_ERROR,
                                      stderr="Compiler succeeded but produced no executable file.")

        unit_e = f"exec-{submission_id.hex[:8]}-{uuid.uuid4().hex[:4]}"
        command_to_wrap = cfg["run"]
        bwrap_args_e = ["--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                        "--ro-bind", "/lib64", "/lib64", "--bind", td, "/sandbox",
                        "--proc", "/proc", "--dev", "/dev", "--chdir", "/sandbox",
                        "--unshare-pid", "--unshare-net",
                        PYTHON3, "/sandbox/wrapper.py"] + command_to_wrap

        eres = await asyncio.get_running_loop().run_in_executor(
            blocking_executor, _systemd_bwrap_run, unit_e,
            problem.time_limit_sec, problem.memory_limit_mb, bwrap_args_e
        )

        exec_ms, mem_kb, exit_code = 0.0, 0, 0
        try:
            with open(res_log_f, 'r') as f:
                for line in f:
                    if line.startswith("EXIT_CODE:"): exit_code = int(line.strip().split(':')[1])
                    if line.startswith("WALL_S:"): exec_ms = round(float(line.strip().split(':')[1]) * 1000, 2)
                    if line.startswith("MEM_KB:"): mem_kb = int(line.strip().split(':')[1])
        except (IOError, IndexError, ValueError):
            pass

        sysd = eres.get("systemd_result")
        status: SubmissionStatus
        if sysd == "timeout":
            status = SubmissionStatus.TIME_LIMIT_EXCEEDED
            exec_ms = float(problem.time_limit_sec * 1000)
        elif sysd == "oom-kill":
            status = SubmissionStatus.MEMORY_LIMIT_EXCEEDED
        elif exit_code != 0:
            status = SubmissionStatus.RUNTIME_ERROR
        else:
            diffc = await asyncio.get_running_loop().run_in_executor(blocking_executor, _diff_files, out_f, exp_f)
            status = SubmissionStatus.ACCEPTED if diffc == 0 else SubmissionStatus.WRONG_ANSWER

        stderr_msg, stdout_content = None, None
        if os.path.exists(err_f):
            with open(err_f, 'r', errors='ignore') as f: stderr_msg = f.read(4096).strip() or None
        if status == SubmissionStatus.WRONG_ANSWER and os.path.exists(out_f):
            with open(out_f, 'r', errors='ignore') as f: stdout_content = f.read(4096).strip() or None

        return TestCaseResult(
            test_case_name=test_case.name, status=status, stdout=stdout_content, stderr=stderr_msg,
            execution_time_ms=exec_ms, memory_used_kb=mem_kb
        )
    except Exception as e:
        traceback.print_exc()
        return TestCaseResult(test_case_name=test_case.name, status=SubmissionStatus.INTERNAL_ERROR,
                              stderr=f"Sandbox critical error: {e}", execution_time_ms=0.0, memory_used_kb=0)
    finally:
        shutil.rmtree(td, ignore_errors=True)


async def run_generator_in_sandbox(
        problem: Problem,
        language: str = "python"
) -> Dict[str, Any]:
    lang = language.lower()
    cfg = LANGUAGE_CONFIG.get(lang)
    if not cfg:
        return {"input": None, "output": None,
                "error": f"Unsupported generator language: {language}",
                "status": "error"}

    if not problem.generator_code:
        return {"input": None, "output": None,
                "error": "Generator code not found in problem object.",
                "status": "error"}

    generator_code = problem.generator_code
    td = tempfile.mkdtemp(prefix=f"generator_{uuid.uuid4().hex[:8]}_")

    try:
        results_dir = os.path.join(td, "results")
        os.makedirs(results_dir, exist_ok=True)
        out_f = os.path.join(results_dir, "user.stdout")
        err_f = os.path.join(results_dir, "user.stderr")
        res_log_f = os.path.join(td, "res.log")
        wrapper_f = os.path.join(td, "wrapper.py")

        with open(os.path.join(td, "user_code" + cfg["ext"]), 'w') as f:
            f.write(generator_code)
        with open(wrapper_f, 'w') as f:
            f.write(WRAPPER_SCRIPT)

        unit_g = f"gen-{uuid.uuid4().hex[:8]}"
        command_to_wrap = cfg["run"]
        bwrap_args_g = ["--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                        "--ro-bind", "/lib64", "/lib64", "--bind", td, "/sandbox",
                        "--proc", "/proc", "--dev", "/dev", "--chdir", "/sandbox",
                        "--unshare-pid", "--unshare-net",
                        PYTHON3, "/sandbox/wrapper.py"] + command_to_wrap

        g_tlim_sec = problem.generator_time_limit_sec or 5.0
        g_mlim_mb = problem.generator_memory_limit_mb or 256
        g_tlim_sec = max(1.0, g_tlim_sec)

        gres = await asyncio.get_running_loop().run_in_executor(
            blocking_executor, _systemd_bwrap_run, unit_g,
            int(g_tlim_sec), g_mlim_mb, bwrap_args_g
        )

        exec_ms, mem_kb, exit_code = 0.0, 0, 0
        try:
            with open(res_log_f, 'r') as f:
                for line in f:
                    if line.startswith("EXIT_CODE:"): exit_code = int(line.strip().split(':')[1])
                    if line.startswith("WALL_S:"): exec_ms = round(float(line.strip().split(':')[1]) * 1000, 2)
                    if line.startswith("MEM_KB:"): mem_kb = int(line.strip().split(':')[1])
        except (IOError, IndexError, ValueError):
            pass

        sysd = gres.get("systemd_result")
        error_content: Optional[str] = None
        status_reason = f"Systemd: {sysd}, Exit: {exit_code}, Time: {exec_ms}ms, Mem: {mem_kb}KB"

        if sysd == "timeout":
            error_content = f"Generator Timed Out ({g_tlim_sec}s). {status_reason}"
        elif sysd == "oom-kill":
            error_content = f"Generator Memory Limit Exceeded ({g_mlim_mb}MB). {status_reason}"
        elif exit_code != 0:
            error_content = f"Generator script exited with error code {exit_code}. {status_reason}"

        input_content, output_content = None, None
        if not error_content:
            if os.path.exists(out_f):
                with open(out_f, 'r', errors='ignore') as f: input_content = f.read(8192).strip() or None
            if os.path.exists(err_f):
                with open(err_f, 'r', errors='ignore') as f: output_content = f.read(8192).strip() or None
        elif os.path.exists(err_f):
            with open(err_f, 'r', errors='ignore') as f:
                script_error = f.read(4096).strip()
                if script_error:
                    error_content += f"\n---\nGenerator Script Error Output:\n{script_error}"

        return {
            "input": input_content, "output": output_content, "error": error_content,
            "execution_time_ms": exec_ms, "memory_used_kb": mem_kb,
            "status": "success" if error_content is None else "error"
        }
    except Exception as e:
        traceback.print_exc()
        return {
            "input": None, "output": None,
            "error": f"Generator sandbox critical error: {e}",
            "execution_time_ms": 0.0, "memory_used_kb": 0, "status": "internal_error"
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

            for i, tc in enumerate(sorted(problem.test_cases, key=lambda x: x.name)):
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
