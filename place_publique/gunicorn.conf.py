# Configuration Gunicorn pour Place Publique / FlowView
# Utilisé en production via : gunicorn --config gunicorn.conf.py app:create_app()

bind = "0.0.0.0:5000"
workers = 2
worker_class = "sync"
timeout = 120
keepalive = 5
errorlog = "-"
accesslog = "-"
loglevel = "info"
# Préchargement de l'application pour économiser la mémoire entre workers
preload_app = True
