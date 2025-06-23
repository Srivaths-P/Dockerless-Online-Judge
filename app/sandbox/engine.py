import asyncio
import os
import shutil
import tempfile
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

from pydantic import BaseModel

from app.sandbox.common import (
    LANGUAGE_CONFIG, EXECUTION_WRAPPER, COMPILE_WRAPPER, PYTHON3,
    _systemd_bwrap_run
)

MAX_THREADS = (os.cpu_count() or 2) * 2
blocking_executor = ThreadPoolExecutor(max_workers=MAX_THREADS)


class SandboxResult(BaseModel):
    status: str
    exit_code: int = -1
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    execution_time_ms: float = 0.0
    memory_used_kb: int = 0
    compilation_stderr: Optional[str] = None


async def run_sandboxed(
        code: str,
        language: str,
        run_input: Optional[str] = None,
        time_limit_sec: int = 5,
        memory_limit_mb: int = 128,
        unit_name_prefix: str = "sandbox",
        extra_bind_files: Optional[List[Tuple[str, str]]] = None,
        cmd_args: Optional[List[str]] = None
) -> SandboxResult:
    lang = language.lower()
    cfg = LANGUAGE_CONFIG.get(lang)
    if not cfg:
        return SandboxResult(status='internal_error', stderr=f"Unsupported language: {language}")

    td = tempfile.mkdtemp(prefix=f"{unit_name_prefix}_{uuid.uuid4().hex[:8]}_")

    try:
        results_dir = os.path.join(td, "results")
        os.makedirs(results_dir, exist_ok=True)
        out_f = os.path.join(results_dir, "user.stdout")
        err_f = os.path.join(results_dir, "user.stderr")
        res_log_f = os.path.join(td, "res.log")
        in_f = os.path.join(td, "input.txt")
        wrapper_f = os.path.join(td, "wrapper.py")

        with open(os.path.join(td, "user_code" + cfg["ext"]), 'w') as f:
            f.write(code)
        if run_input is not None:
            with open(in_f, 'w') as f: f.write(run_input)

        compilation_stderr = None
        if cfg["compile"]:
            unit_c = f"{unit_name_prefix}-compile-{uuid.uuid4().hex[:4]}"
            with open(wrapper_f, 'w') as f:
                f.write(COMPILE_WRAPPER)
            bwrap_args_c = ["--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                            "--ro-bind", "/lib64", "/lib64", "--bind", td, "/sandbox",
                            "--proc", "/proc", "--dev", "/dev", "--chdir", "/sandbox",
                            "--unshare-user", "--unshare-pid", "--unshare-net",
                            PYTHON3, "/sandbox/wrapper.py"] + cfg["compile"]
            cres = await asyncio.get_running_loop().run_in_executor(
                blocking_executor, _systemd_bwrap_run, unit_c, 30, 512, bwrap_args_c
            )
            compile_exit_code = -1
            try:
                with open(res_log_f, 'r') as f:
                    for line in f:
                        if line.startswith("EXIT_CODE:"):
                            compile_exit_code = int(line.strip().split(':')[1])
            except (IOError, IndexError, ValueError):
                pass
            if cres.get("systemd_result") != "success" or compile_exit_code != 0:
                if os.path.exists(err_f):
                    with open(err_f, 'r', errors='ignore') as f:
                        compilation_stderr = f.read(4096).strip()
                if cres.get("systemd_result") == "timeout":
                    compilation_stderr = "Compilation Timed Out.\n" + (compilation_stderr or "")
                elif cres.get("systemd_result") == "oom-kill":
                    compilation_stderr = "Compilation Memory Limit Exceeded.\n" + (compilation_stderr or "")
                return SandboxResult(status='compilation_error',
                                     compilation_stderr=compilation_stderr or "Compilation failed.")
            executable_path = os.path.join(td, "user_exec")
            if not os.path.exists(executable_path):
                return SandboxResult(status='internal_error',
                                     stderr="Compiler succeeded but produced no executable file.")
            os.chmod(executable_path, 0o755)

        with open(wrapper_f, 'w') as f:
            f.write(EXECUTION_WRAPPER)

        unit_e = f"{unit_name_prefix}-exec-{uuid.uuid4().hex[:4]}"
        command_to_wrap = cfg["run"]
        bwrap_args_e = ["--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                        "--ro-bind", "/lib64", "/lib64", "--bind", td, "/sandbox",
                        "--proc", "/proc", "--dev", "/dev", "--chdir", "/sandbox",
                        "--unshare-user", "--unshare-pid", "--unshare-net"]

        if extra_bind_files:
            for host_path, sandbox_path in extra_bind_files:
                bwrap_args_e.extend(["--ro-bind", host_path, sandbox_path])

        final_command = command_to_wrap + (cmd_args or [])
        bwrap_args_e.extend([PYTHON3, "/sandbox/wrapper.py"] + final_command)

        eres = await asyncio.get_running_loop().run_in_executor(
            blocking_executor, _systemd_bwrap_run, unit_e,
            time_limit_sec, memory_limit_mb, bwrap_args_e
        )

        exec_ms, mem_kb, exit_code = 0.0, 0, -1
        try:
            with open(res_log_f, 'r') as f:
                for line in f:
                    if line.startswith("EXIT_CODE:"): exit_code = int(line.strip().split(':')[1])
                    if line.startswith("WALL_S:"): exec_ms = round(float(line.strip().split(':')[1]) * 1000, 2)
                    if line.startswith("MEM_KB:"): mem_kb = int(line.strip().split(':')[1])
        except (IOError, IndexError, ValueError):
            pass

        sysd = eres.get("systemd_result")
        status = 'internal_error'
        if sysd == "timeout":
            status = 'timeout'
            exec_ms = float(time_limit_sec * 1000)
        elif sysd == "oom-kill":
            status = 'oom-kill'
        elif sysd == "success":
            status = 'success'

        stdout_content, stderr_content = None, None
        if os.path.exists(out_f):
            with open(out_f, 'r', errors='ignore') as f:
                stdout_content = f.read()
        if os.path.exists(err_f):
            with open(err_f, 'r', errors='ignore') as f:
                stderr_content = f.read(4096).strip() or None

        return SandboxResult(
            status=status,
            exit_code=exit_code,
            stdout=stdout_content,
            stderr=stderr_content,
            execution_time_ms=exec_ms,
            memory_used_kb=mem_kb,
            compilation_stderr=compilation_stderr
        )
    except Exception as e:
        traceback.print_exc()
        return SandboxResult(status='internal_error', stderr=f"Sandbox engine critical error: {e}")
    finally:
        shutil.rmtree(td, ignore_errors=True)
