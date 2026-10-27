import os
import uuid
import asyncio
import httpx
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from contextvars import ContextVar

SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown-service")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
DOWNSTREAM_URLS = os.getenv("DOWNSTREAM_URLS", "")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://registry:8000/services/")

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
http_client: httpx.AsyncClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    http_client = httpx.AsyncClient(limits=limits)
    
    downstreams = [url.strip().replace("http://", "").split(":")[0] for url in DOWNSTREAM_URLS.split(",") if url.strip()]
    payload = {"name": SERVICE_NAME, "version": APP_VERSION, "dependencies": downstreams}
    
    # Retry loop strictly for initial registration
    max_retries = 5
    for attempt in range(max_retries):
        try:
            resp = await http_client.post(REGISTRY_URL, json=payload, timeout=5.0)
            resp.raise_for_status()
            print(f"[{SERVICE_NAME}] Successfully registered with Central Registry.")
            break # Success, exit loop
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[{SERVICE_NAME}] CRITICAL FAILURE: Could not register after {max_retries} attempts. Continuing as ghost node.")
            else:
                wait_time = 2 ** attempt
                print(f"[{SERVICE_NAME}] Registry unavailable, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
        
    yield
    
    await http_client.aclose()

app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    corr_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    correlation_id_var.set(corr_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = corr_id
    return response

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