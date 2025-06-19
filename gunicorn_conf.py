import os
import signal
import psutil

RELOAD_SIGNAL_FILE = "/tmp/gunicorn_doj_reload.sig"


def on_exit(server):
    if os.path.exists(RELOAD_SIGNAL_FILE):
        print("Reload signal file found. Sending SIGHUP to master.")
        master_pid = os.getppid()

        for proc in psutil.process_iter(['pid', 'ppid']):
            if proc.info['ppid'] == master_pid:
                master_pid = proc.info['pid']
                break

        os.kill(master_pid, signal.SIGHUP)
        os.remove(RELOAD_SIGNAL_FILE)
