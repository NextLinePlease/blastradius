import os
import uuid
import asyncio
import httpx
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from contextvars import ContextVar

SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown-service")
DOWNSTREAM_URLS = os.getenv("DOWNSTREAM_URLS", "")

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

# This is our Singleton HTTP client. It starts as None.
http_client: httpx.AsyncClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP LOGIC ---
    global http_client
    # We configure connection pooling limits. 
    # max_keepalive_connections keeps sockets warm for reuse.
    # max_connections prevents the client from overwhelming the OS.
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    http_client = httpx.AsyncClient(limits=limits)
    print(f"[{SERVICE_NAME}] Initialized global HTTP client pool.")
    
    yield # The application runs and serves requests while paused here.
    
    # --- SHUTDOWN LOGIC ---
    await http_client.aclose()
    print(f"[{SERVICE_NAME}] Closed global HTTP client pool.")

app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    corr_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    correlation_id_var.set(corr_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = corr_id
    return response

async def fetch_downstream(url: str):
    """Now relies on the global http_client instead of creating a new one."""
    corr_id = correlation_id_var.get()
    headers = {"x-correlation-id": corr_id}
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = await http_client.get(f"{url}/api/data", headers=headers, timeout=4.0)
            resp.raise_for_status()
            return resp.json()
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
        # We no longer instantiate httpx.AsyncClient() here. 
        # We just fire the requests using the warm, global pool.
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