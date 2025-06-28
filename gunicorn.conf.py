"""
Gunicorn configuration for Railway deployment
Optimized for video streaming with high concurrency
"""
import os
import multiprocessing

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 300  # Increased timeout for video streaming
keepalive = 30  # Increased keep-alive for mobile players
graceful_timeout = 60

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "isolated-video-streaming"

# Server mechanics
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (disabled for Railway)
keyfile = None
certfile = None

# Performance tuning for video streaming
preload_app = True
sendfile = True

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Application-specific settings
raw_env = [
    f"PORT={os.environ.get('PORT', 5000)}",
    f"FLASK_ENV={os.environ.get('FLASK_ENV', 'production')}",
    f"SESSION_SECRET={os.environ.get('SESSION_SECRET', 'fallback-secret-key')}",
]

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting Isolated Fast Video Streaming Server")
    server.log.info(f"Binding to {bind}")
    server.log.info(f"Workers: {workers}")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading server...")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info(f"Worker {worker.pid} received INT or QUIT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info(f"Worker {worker.pid} is being forked")

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(f"Worker {worker.pid} has been forked")

def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal."""
    worker.log.info(f"Worker {worker.pid} received SIGABRT signal")
