def post_worker_init(worker):
    print(f"Gunicorn worker {worker.pid}: Initializing and loading contest data.")
    from app.services.contest_service import load_server_data
    load_server_data()
