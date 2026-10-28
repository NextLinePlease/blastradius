import os
import uuid
import asyncio
import time
import httpx
import redis.asyncio as redis
from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from contextvars import ContextVar

SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown-service")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
DOWNSTREAM_URLS = os.getenv("DOWNSTREAM_URLS", "")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://registry:8000/services/")
# Default points to the Docker Compose internal DNS for Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
http_client: httpx.AsyncClient = None
redis_client: redis.Redis = None

async def push_metric_to_redis(corr_id: str, status: int, latency_ms: float):
    """Fire-and-forget telemetry pusher with memory capping."""
    if not redis_client:
        return
    try:
        await redis_client.xadd(
            "telemetry:requests",
            {
                "service": SERVICE_NAME,
                "version": APP_VERSION,
                "correlation_id": corr_id,
                "status": str(status),
                "latency_ms": f"{latency_ms:.2f}"
            },
            # NEW: Keep only the newest 100,000 events. 
            # approximate=True (~ operator in raw Redis) makes the truncation vastly more CPU efficient.
            maxlen=100000, 
            approximate=True
        )
    except Exception as e:
        print(f"[{SERVICE_NAME}] Telemetry drop: Failed to reach Redis: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client, redis_client
    
    # 1. Initialize HTTP Pool
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    http_client = httpx.AsyncClient(limits=limits)
    
    # 2. Initialize Redis Connection Pool
    # decode_responses=True ensures Redis returns standard Python strings, not raw bytes.
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    
    # 3. Dynamic Registration
    downstreams = [url.strip().replace("http://", "").split(":")[0] for url in DOWNSTREAM_URLS.split(",") if url.strip()]
    payload = {"name": SERVICE_NAME, "version": APP_VERSION, "dependencies": downstreams}
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            resp = await http_client.post(REGISTRY_URL, json=payload, timeout=5.0)
            resp.raise_for_status()
            print(f"[{SERVICE_NAME}] Successfully registered with Central Registry.")
            break
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[{SERVICE_NAME}] CRITICAL FAILURE: Registration failed. Continuing as ghost node.")
            else:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
                
    yield
    
    # Graceful shutdown of both connection pools
    await http_client.aclose()
    await redis_client.aclose()

app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)

@app.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    # time.perf_counter() is immune to system clock updates (NTP syncs), making it strictly 
    # superior to time.time() for measuring microsecond latency differences.
    start_time = time.perf_counter()
    
    corr_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    correlation_id_var.set(corr_id)
    
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Correlation-ID"] = corr_id
        return response
    except Exception as e:
        # If the route crashes completely, we still want to record the 500 error in Redis.
        raise e
    finally:
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        # ASYNCHRONOUS DECOUPLING:
        # We do NOT use `await push_metric...`. Awaiting would force the user's HTTP request 
        # to wait for the Redis network trip before getting their JSON payload.
        # create_task schedules the push on the event loop to run independently in the background.
        asyncio.create_task(push_metric_to_redis(corr_id, status_code, latency_ms))

async def fetch_downstream(url: str):
    corr_id = correlation_id_var.get()
    headers = {"x-correlation-id": corr_id}
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = await http_client.get(f"{url}/api/data", headers=headers, timeout=4.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.PoolTimeout:
            return {"error": "Connection pool exhausted", "service": url, "status": "overloaded"}
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": str(e), "service": url, "status": "degraded"}
            await asyncio.sleep(2 ** attempt)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": SERVICE_NAME}

@app.get("/api/data")
async def handle_request():
    corr_id = correlation_id_var.get()
    downstreams = [url.strip() for url in DOWNSTREAM_URLS.split(",") if url.strip()]
    
    results = {}
    if downstreams:
        tasks = [fetch_downstream(url) for url in downstreams]
        responses = await asyncio.gather(*tasks)
        for url, response in zip(downstreams, responses):
            name = url.replace("http://", "").split(":")[0]
            results[name] = response

    return {
        "service": SERVICE_NAME,
        "correlation_id": corr_id,
        "dependencies": results
    }