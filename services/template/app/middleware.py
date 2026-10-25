import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.logging_config import request_id_var

log = logging.getLogger("request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = (
            request.headers.get("x-request-id")
            or str(uuid.uuid4())
        )

        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status = 500

        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            log.exception("unhandled exception")
            response = JSONResponse(
                {
                    "detail": "internal error",
                    "request_id": request_id,
                },
                status_code=500,
            )

        duration_ms = round(
            (time.perf_counter() - start) * 1000, 2
        )
        response.headers["X-Request-ID"] = request_id

        level = (
            logging.DEBUG
            if request.url.path == "/health"
            else logging.INFO
        )

        try:
            log.log(
                level,
                "request",
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": status,
                        "duration_ms": duration_ms,
                    }
                },
            )
        finally:
            request_id_var.reset(token)

        return response
