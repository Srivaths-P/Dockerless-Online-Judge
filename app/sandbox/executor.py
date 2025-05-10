import asyncio
import os
import resource
import shutil
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.problem import Problem, TestCase
from app.schemas.submission import SubmissionStatus, TestCaseResult

BWRAP_PATH = "/usr/bin/bwrap"
PYTHON3_PATH = "/usr/bin/python3"
GCC_PATH = "/usr/bin/gcc"
GPP_PATH = "/usr/bin/g++"

LANGUAGE_CONFIG: Dict[str, Dict[str, Any]] = {
    "python": {
        "extension": ".py",
        "compiled": False,
        "compile_cmd_template": None,
        "execution_cmd_template": [PYTHON3_PATH, "/sandbox/user_code.py"]
    },
    "c": {
        "extension": ".c",
        "compiled": True,
        "compile_cmd_template": [GCC_PATH, "/sandbox/user_code.c", "-o", "/sandbox/user_exec", "-O2", "-std=c11",
                                 "-lm"],
        "execution_cmd_template": ["/sandbox/user_exec"]
    },
    "c++": {
        "extension": ".cpp",
        "compiled": True,
        "compile_cmd_template": [GPP_PATH, "/sandbox/user_code.cpp", "-o", "/sandbox/user_exec", "-O2", "-std=c++17"],
        "execution_cmd_template": ["/sandbox/user_exec"]
    }
}

MAX_WORKERS = (os.cpu_count() or 2) * 2
thread_pool_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


def make_bwrap_args(
        temp_dir: str,
        writable: bool,
        tmpfs_size: Optional[str]
) -> List[str]:
    """
    Build bubblewrap arguments.
    - writable: True → mount temp_dir read-write; False → read-only.
    - tmpfs_size: e.g. "1G" for larger tmpfs, or None for default small tmpfs.
    """
    args = [
        BWRAP_PATH,
        "--unshare-all", "--proc", "/proc", "--dev", "/dev",
    ]
    if tmpfs_size:
        args += ["--tmpfs", f"/tmp:size={tmpfs_size}"]
    else:
        args += ["--tmpfs", "/tmp"]

    args += [
        "--die-with-parent",
        f"--{'bind' if writable else 'ro-bind'}", temp_dir, "/sandbox",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/usr/bin", "/usr/bin",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/bin", "/bin",
        "--chdir", "/sandbox"
    ]
    return args


def _run_and_measure(
        bwrap_args: List[str],
        inner_cmd: List[str],
        stdin_path: Optional[str],
        stdout_path: str,
        stderr_path: str,
        time_limit_sec: Optional[int],
        mem_limit_mb: Optional[int],
        is_compile: bool
) -> Tuple[int, bool, int]:
    """
    Run `bwrap_args + inner_cmd` with resource limits.
    Returns (return_code, timed_out, peak_rss_kb).
    """

    def _limits():
        if is_compile:

            resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        else:

            resource.setrlimit(resource.RLIMIT_CPU, (time_limit_sec, time_limit_sec + 1))
            as_bytes = mem_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (as_bytes, as_bytes))

        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
        except Exception:
            pass

    stdin_f = open(stdin_path, 'rb') if stdin_path else subprocess.DEVNULL
    with open(stdout_path, 'wb') as out_f, open(stderr_path, 'wb') as err_f:
        proc = subprocess.Popen(
            bwrap_args + inner_cmd,
            stdin=stdin_f,
            stdout=out_f,
            stderr=err_f,
            preexec_fn=_limits
        )
        try:
            timeout = 30 if is_compile else (time_limit_sec + 1)
            proc.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            timed_out = True

    if stdin_path:
        try:
            stdin_f.close()
        except Exception:
            pass

    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    peak_rss_kb = usage.ru_maxrss

    return proc.returncode, timed_out, peak_rss_kb


async def run_code_in_sandbox(
        submission_id: uuid.UUID,
        code: str,
        problem: Problem,
        test_case: TestCase,
        language: str
) -> TestCaseResult:
    start_ns = time.perf_counter_ns()
    loop = asyncio.get_event_loop()

    key = language.lower()
    if key not in LANGUAGE_CONFIG:
        return TestCaseResult(
            test_case_name=test_case.name,
            status=SubmissionStatus.INTERNAL_ERROR,
            stdout=None,
            stderr=f"Unsupported language: {language}",
            execution_time_ms=0.0,
            memory_used_kb=None
        )

    cfg = LANGUAGE_CONFIG[key]
    ext = cfg["extension"]
    is_comp = cfg["compiled"]
    comp_cmd = cfg["compile_cmd_template"]
    run_cmd = cfg["execution_cmd_template"]

    temp_dir = tempfile.mkdtemp(prefix=f"judge_{submission_id.hex[:6]}_")
    code_path = os.path.join(temp_dir, f"user_code{ext}")
    input_path = os.path.join(temp_dir, "input.txt")
    stdout_path = os.path.join(temp_dir, "stdout.txt")
    stderr_path = os.path.join(temp_dir, "stderr.txt")

    with open(code_path, 'w') as f:
        f.write(code)
    with open(input_path, 'w') as f:
        if test_case.input_content: f.write(test_case.input_content)
    open(stdout_path, 'w').close()
    open(stderr_path, 'w').close()

    total_compile_ns = 0
    if is_comp:
        bwrap_args = make_bwrap_args(temp_dir, writable=True, tmpfs_size="1G")
        t0 = time.perf_counter_ns()
        code_ret, timed_out, mem_c = await loop.run_in_executor(
            thread_pool_executor,
            _run_and_measure,
            bwrap_args,
            comp_cmd,
            None,
            stdout_path,
            stderr_path,
            problem.time_limit_sec,
            problem.memory_limit_mb,
            True
        )
        total_compile_ns = time.perf_counter_ns() - t0

        if timed_out or code_ret != 0:
            err = open(stderr_path).read().strip() or f"Compilation failed ({code_ret})"
            shutil.rmtree(temp_dir, ignore_errors=True)
            return TestCaseResult(
                test_case_name=test_case.name,
                status=SubmissionStatus.COMPILATION_ERROR,
                stdout=None,
                stderr=err,
                execution_time_ms=round((time.perf_counter_ns() - start_ns) / 1e6, 2),
                memory_used_kb=mem_c
            )

        open(stdout_path, 'w').close()
        open(stderr_path, 'w').close()

    bwrap_args = make_bwrap_args(temp_dir, writable=False, tmpfs_size=None)
    code_ret, timed_out, peak_mem_kb = await loop.run_in_executor(
        thread_pool_executor,
        _run_and_measure,
        bwrap_args,
        run_cmd,
        input_path,
        stdout_path,
        stderr_path,
        problem.time_limit_sec,
        problem.memory_limit_mb,
        False
    )

    out_txt = open(stdout_path).read().strip() if os.path.exists(stdout_path) else ""
    err_txt = open(stderr_path).read().strip() if os.path.exists(stderr_path) else ""

    if timed_out or code_ret == -9:
        status = SubmissionStatus.TIME_LIMIT_EXCEEDED
    elif code_ret < 0:
        status = SubmissionStatus.RUNTIME_ERROR
    elif code_ret != 0:
        status = SubmissionStatus.RUNTIME_ERROR
    else:
        expected = (test_case.output_content or "").strip()
        status = SubmissionStatus.ACCEPTED if out_txt == expected else SubmissionStatus.WRONG_ANSWER

    shutil.rmtree(temp_dir, ignore_errors=True)
    total_ns = time.perf_counter_ns() - start_ns - total_compile_ns
    exec_ms = round(total_ns / 1e6, 2)

    return TestCaseResult(
        test_case_name=test_case.name,
        status=status,
        stdout=out_txt if status == SubmissionStatus.WRONG_ANSWER else None,
        stderr=err_txt if status == SubmissionStatus.RUNTIME_ERROR else None,
        execution_time_ms=exec_ms,
        memory_used_kb=peak_mem_kb
    )
