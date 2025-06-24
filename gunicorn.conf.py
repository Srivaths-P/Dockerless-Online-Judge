import os
from uvicorn_worker import UvicornWorker


class MyUvicornWorker(UvicornWorker):
    CONFIG_KWARGS = {
        "forwarded_allow_ips": "130.211.0.0/22,35.191.0.0/16",
    }


bind = "unix:doj.sock"
umask = 0o007
workers = 4
worker_class = "gunicorn.conf.MyUvicornWorker"


def when_ready(server):
    pid = os.getpid()
    os.environ['GUNICORN_PID'] = str(pid)
    server.log.info(f"Gunicorn master process (PID: {pid}) is ready. Setting GUNICORN_PID.")


def post_worker_init(worker):
    print(f"Gunicorn worker {worker.pid}: Initializing and loading contest data.")
    from app.services.contest_service import load_server_data
    load_server_data()
