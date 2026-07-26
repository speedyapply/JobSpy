"""
Configuração do Celery para processamento assíncrono de candidaturas.
Usa Redis como broker e backend de resultados.
"""

import os
from celery import Celery

# A URL do Redis pode vir de uma variável de ambiente ou do .env
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "jobspy",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],  # Onde as tasks serão registradas
)

# Configurações opcionais
celery_app.conf.update(
    task_track_started=True,        # Permite ver status "STARTED"
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_acks_late=True,            # Re-entrega se o worker morrer
    worker_prefetch_multiplier=1,   # Um task por vez
    result_expires=60 * 60 * 24,    # Resultados expiram em 24h
)
