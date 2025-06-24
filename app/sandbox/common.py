import os
import subprocess
from typing import Any, Dict, Optional

SUPPORTED_IDE_LANGUAGES = ["python", "c++", "c"]

BWRAP = "/usr/bin/bwrap"
PYTHON3 = "/usr/bin/python3"
GCC = "/usr/bin/gcc"
GPP = os.getenv("GPP_PATH", "/usr/bin/g++")

EXECUTION_WRAPPER = """
import os
import resource
import sys
import signal
import time

command = sys.argv[1:]
stdin_path = '/workspace/input.txt'
stdout_path = '/workspace/user.stdout'
stderr_path = '/workspace/user.stderr'
res_log_path = '/tmp/res.log'

cpu_limit_sec = int(os.environ['CPU_LIMIT_S'])

if os.path.exists(stdin_path):
    stdin_fd = os.open(stdin_path, os.O_RDONLY)
else:
    stdin_fd = os.open(os.devnull, os.O_RDONLY)

stdout_fd = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
stderr_fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)

pid = os.fork()

if pid == 0:
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit_sec, cpu_limit_sec))
        os.dup2(stdin_fd, sys.stdin.fileno())
        os.dup2(stdout_fd, sys.stdout.fileno())
        os.dup2(stderr_fd, sys.stderr.fileno())
        os.execv(command[0], command)
    except Exception as e:
        os.write(stderr_fd, f"Wrapper execv error: {e}".encode())
        os._exit(127)
else:
    _pid, status, rusage = os.wait4(pid, 0)

    cpu_time_s = rusage.ru_utime + rusage.ru_stime
    mem_kb = rusage.ru_maxrss

    exit_code = -1
    signal_num = 0

    if os.WIFSIGNALED(status):
        signal_num = os.WTERMSIG(status)
        exit_code = -signal_num
    elif os.WIFEXITED(status):
        exit_code = os.WEXITSTATUS(status)

    with open(res_log_path, 'w') as f:
        f.write(f"EXIT_CODE:{exit_code}\\n")
        f.write(f"SIGNAL:{signal_num}\\n")
        f.write(f"CPU_S:{cpu_time_s:.4f}\\n")
        f.write(f"MEM_KB:{mem_kb}\\n")

    os.close(stdin_fd)
    os.close(stdout_fd)
    os.close(stderr_fd)
"""

COMPILE_WRAPPER = EXECUTION_WRAPPER.replace("'/workspace/input.txt'", "'/dev/null'")

LANGUAGE_CONFIG: Dict[str, Dict[str, Any]] = {
    "python": {
        "ext": ".py",
        "compile": None,
        "run": [PYTHON3, "/workspace/user_code.py"]
    },
    "c": {
        "ext": ".c",
        "compile": [GCC, "/workspace/user_code.c", "-o", "/workspace/user_exec",
                    "-O2", "-std=c11", "-lm"],
        "run": ["/workspace/user_exec"]
    },
    "c++": {
        "ext": ".cpp",
        "compile": [GPP, "/workspace/user_code.cpp", "-o", "/workspace/user_exec",
                    "-O2", "-std=c++17"],
        "run": ["/workspace/user_exec"]
    },
}


def _make_systemd_bwrap_cmd(
        unit: str,
        tlim: int,
        mlim: int,
        bwrap_args: list
) -> list:
    wall_clock_safety_margin = 5
    wall_tlim = int(tlim * 2 + wall_clock_safety_margin)

    cmd = [
              "systemd-run", "--quiet", "--scope", "--user",
              f"--unit={unit}", "--slice=judge.slice",
              "-p", "TasksMax=64",
              "-p", f"RuntimeMaxSec={wall_tlim}",
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
        env: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    full_cmd = _make_systemd_bwrap_cmd(unit, tlim, mlim, bwrap_args)
    subprocess.run(full_cmd, check=False, env=env)
    systemd_result_str = "unknown"
    try:
        scope_unit_name = f"{unit}.scope"
        show_cmd = ["systemctl", "show", "--user", scope_unit_name, "-p", "Result", "--value"]
        res = subprocess.run(show_cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            systemd_result_str = res.stdout.strip()
    except Exception as e:
        print(f"Failed to get systemd result for {unit}: {e}")
    subprocess.run(["systemctl", "--user", "reset-failed", f"{unit}.scope"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    subprocess.run(["systemctl", "--user", "stop", f"{unit}.scope"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return {"systemd_result": systemd_result_str}


def diff_files(out_path: str, exp_path: str) -> int:
    if not os.path.exists(out_path): open(out_path, 'w').close()
    if not os.path.exists(exp_path): open(exp_path, 'w').close()
    return subprocess.run(["diff", "-Z", "--strip-trailing-cr", "-q", out_path, exp_path],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
