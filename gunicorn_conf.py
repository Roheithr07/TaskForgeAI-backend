import multiprocessing
import os

# Gunicorn configuration for TaskForge AI production deployment
bind = os.getenv("BIND", "0.0.0.0:8000")

# Recommended: 2-4 workers per CPU core, with a configurable override
workers_per_core_str = os.getenv("WORKERS_PER_CORE", "1")
web_concurrency_str = os.getenv("WEB_CONCURRENCY", None)

if web_concurrency_str:
    workers = int(web_concurrency_str)
else:
    cores = multiprocessing.cpu_count()
    workers = max(int(float(workers_per_core_str) * cores), 2)

worker_class = "uvicorn.workers.UvicornWorker"
keepalive = 120
timeout = 180
graceful_timeout = 60

# Logging
loglevel = os.getenv("LOG_LEVEL", "info").lower()
accesslog = "-"
errorlog = "-"
capture_output = True

