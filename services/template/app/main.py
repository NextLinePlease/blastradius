import logging
import os
import time

from fastapi import FastAPI

from app.logging_config import request_id_var, setup_logging
from app.middleware import RequestContextMiddleware

SERVICE_NAME = os.getenv("SERVICE_NAME", "template")

setup_logging(SERVICE_NAME)
log = logging.getLogger(SERVICE_NAME)

app = FastAPI(title=f"{SERVICE_NAME} service")
app.add_middleware(RequestContextMiddleware)

START_TIME = time.time()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/")
def root():
    log.info("root endpoint called")
    return {
        "service": SERVICE_NAME,
        "request_id": request_id_var.get(),
    }
