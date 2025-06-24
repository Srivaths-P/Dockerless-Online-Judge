import asyncio
import os
import shutil
import signal
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

    host_td = tempfile.mkdtemp(prefix=f"{unit_name_prefix}_{uuid.uuid4().hex[:8]}_")

    try:
        host_workspace_dir = os.path.join(host_td, "workspace")
        os.makedirs(host_workspace_dir, exist_ok=True)

        host_wrapper_f = os.path.join(host_td, "wrapper.py")
        host_res_log_f = os.path.join(host_td, "res.log")

        host_user_code_f = os.path.join(host_workspace_dir, "user_code" + cfg["ext"])
        host_input_f = os.path.join(host_workspace_dir, "input.txt")
        host_stdout_f = os.path.join(host_workspace_dir, "user.stdout")
        host_stderr_f = os.path.join(host_workspace_dir, "user.stderr")

        open(host_res_log_f, 'w').close()

        with open(host_user_code_f, 'w') as f:
            f.write(code)
        if run_input is not None:
            with open(host_input_f, 'w') as f: f.write(run_input)

        sandbox_wrapper_path = "/judge/wrapper.py"

        compilation_stderr = None
        if cfg["compile"]:
            unit_c = f"{unit_name_prefix}-compile-{uuid.uuid4().hex[:4]}"
            with open(host_wrapper_f, 'w') as f:
                f.write(COMPILE_WRAPPER)

            bwrap_args_c = [
                               "--tmpfs", "/",
                               "--proc", "/proc", "--dev", "/dev",
                               "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64",
                               "/lib64",
                               "--symlink", "usr/bin", "/bin",
                               "--dir", "/tmp",
                               "--dir", "/workspace",
                               "--dir", "/judge",
                               "--bind", host_workspace_dir, "/workspace",
                               "--ro-bind", host_wrapper_f, sandbox_wrapper_path,
                               "--bind", host_res_log_f, "/tmp/res.log",
                               "--chdir", "/workspace",
                               "--unshare-pid", "--unshare-net",
                               PYTHON3, sandbox_wrapper_path,
                           ] + cfg["compile"]

            compile_env = os.environ.copy()
            compile_env['CPU_LIMIT_S'] = '30'
            cres = await asyncio.get_running_loop().run_in_executor(
                blocking_executor, _systemd_bwrap_run, unit_c, 30, 512, bwrap_args_c, compile_env
            )
            compile_exit_code = -1
            try:
                with open(host_res_log_f, 'r') as f:
                    for line in f:
                        if line.startswith("EXIT_CODE:"):
                            compile_exit_code = int(line.strip().split(':')[1])
            except (IOError, IndexError, ValueError):
                pass
            if cres.get("systemd_result") != "success" or compile_exit_code != 0:
                if os.path.exists(host_stderr_f):
                    with open(host_stderr_f, 'r', errors='ignore') as f:
                        compilation_stderr = f.read(4096).strip()
                if cres.get("systemd_result") == "timeout":
                    compilation_stderr = "Compilation Timed Out (Wall Clock).\n" + (compilation_stderr or "")
                elif cres.get("systemd_result") == "oom-kill":
                    compilation_stderr = "Compilation Memory Limit Exceeded.\n" + (compilation_stderr or "")
                return SandboxResult(status='compilation_error',
                                     compilation_stderr=compilation_stderr or "Compilation failed.")

            host_executable_path = os.path.join(host_workspace_dir, "user_exec")
            if not os.path.exists(host_executable_path):
                return SandboxResult(status='internal_error',
                                     stderr="Compiler succeeded but produced no executable file.")
            os.chmod(host_executable_path, 0o755)

        with open(host_wrapper_f, 'w') as f:
            f.write(EXECUTION_WRAPPER)

        unit_e = f"{unit_name_prefix}-exec-{uuid.uuid4().hex[:4]}"
        command_to_wrap = cfg["run"]

        bwrap_args_e = [
            "--tmpfs", "/",
            "--proc", "/proc", "--dev", "/dev",
            "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
            "--symlink", "usr/bin", "/bin",
            "--dir", "/tmp",
            "--dir", "/workspace",
            "--dir", "/judge",
            "--bind", host_workspace_dir, "/workspace",
            "--ro-bind", host_wrapper_f, sandbox_wrapper_path,
            "--bind", host_res_log_f, "/tmp/res.log",
            "--chdir", "/workspace",
            "--unshare-pid", "--unshare-net"
        ]

        if extra_bind_files:
            for host_path, sandbox_path in extra_bind_files:
                bwrap_args_e.extend(["--ro-bind", host_path, sandbox_path])

        final_command = command_to_wrap + (cmd_args or [])
        bwrap_args_e.extend([PYTHON3, sandbox_wrapper_path] + final_command)

        exec_env = os.environ.copy()
        exec_env['CPU_LIMIT_S'] = str(time_limit_sec)
        eres = await asyncio.get_running_loop().run_in_executor(
            blocking_executor, _systemd_bwrap_run, unit_e,
            time_limit_sec, memory_limit_mb, bwrap_args_e, exec_env
        )

        exec_ms, mem_kb, exit_code, signal_num = 0.0, 0, -1, 0
        try:
            with open(host_res_log_f, 'r') as f:
                for line in f:
                    if line.startswith("EXIT_CODE:"): exit_code = int(line.strip().split(':')[1])
                    if line.startswith("SIGNAL:"): signal_num = int(line.strip().split(':')[1])
                    if line.startswith("CPU_S:"): exec_ms = round(float(line.strip().split(':')[1]) * 1000, 2)
                    if line.startswith("MEM_KB:"): mem_kb = int(line.strip().split(':')[1])
        except (IOError, IndexError, ValueError):
            pass

        status = 'internal_error'
        if signal_num != 0:
            if signal_num == signal.SIGXCPU:
                status = 'timeout'
            else:
                status = 'runtime_error'
        elif exit_code == 0:
            status = 'success'
        else:
            status = 'runtime_error'

        sysd = eres.get("systemd_result")
        if sysd == "oom-kill":
            status = 'oom-kill'
        elif sysd == "timeout":
            status = 'timeout'

        if status == 'timeout':
            exec_ms = float(time_limit_sec * 1000)

        stdout_content, stderr_content = None, None
        if os.path.exists(host_stdout_f):
            with open(host_stdout_f, 'r', errors='ignore') as f:
                stdout_content = f.read()
        if os.path.exists(host_stderr_f):
            with open(host_stderr_f, 'r', errors='ignore') as f:
                stderr_content = f.read(4096).strip() or None

        return SandboxResult(
            status=status, exit_code=exit_code, stdout=stdout_content,
            stderr=stderr_content, execution_time_ms=exec_ms,
            memory_used_kb=mem_kb, compilation_stderr=compilation_stderr
        )
    except Exception as e:
        traceback.print_exc()
        return SandboxResult(status='internal_error', stderr=f"Sandbox engine critical error: {e}")
    finally:
        shutil.rmtree(host_td, ignore_errors=True)
