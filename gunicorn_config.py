"""Gunicorn configuration file for production deployment."""
import os
import multiprocessing

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '3000')}"
backlog = 2048

# Worker processes
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'sync'
worker_connections = 1000
timeout = 120  # 2 minutes - needed for AI generation tasks
keepalive = 5

# Logging
accesslog = '-'  # Log to stdout
errorlog = '-'   # Log to stderr
loglevel = os.getenv('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'slack-fathom-crono'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Restart workers after this many requests (helps with memory leaks)
max_requests = 1000
max_requests_jitter = 50

# Preload app for better performance
preload_app = True
