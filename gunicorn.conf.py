import os

wsgi_app = "app.main:app"
preload_app = False


def when_ready(server):
    pid = os.getpid()
    os.environ['GUNICORN_PID'] = str(pid)
    server.log.info(f"Gunicorn master (PID: {pid}) is ready. Setting GUNICORN_PID.")


def post_worker_init(worker):
    print(f"Gunicorn worker {worker.pid}: Initializing and loading contest data.")
    from app.services.contest_service import load_server_data
    load_server_data()


workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
