import os
import uuid
import asyncio
import httpx
from fastapi import FastAPI, Request
from contextvars import ContextVar

SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown-service")
# A comma-separated list of URLs this service depends on
DOWNSTREAM_URLS = os.getenv("DOWNSTREAM_URLS", "")

app = FastAPI(title=SERVICE_NAME)

# ContextVar is async-safe. It stores the Correlation ID for the current request 
# so we don't have to manually pass it as an argument to every single function.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    # 1. EXTRACT OR GENERATE: If the caller provided a trace ID, use it. Otherwise, create a new one.
    corr_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    
    # 2. STORE: Save it in the context variable for the duration of this request.
    correlation_id_var.set(corr_id)
    
    # 3. PROCESS: Let FastAPI route the request to the correct endpoint.
    response = await call_next(request)
    
    # 4. RETURN: Attach the ID to the response headers so the client can see it.
    response.headers["X-Correlation-ID"] = corr_id
    return response

async def fetch_downstream(client: httpx.AsyncClient, url: str):
    corr_id = correlation_id_var.get()
    headers = {"x-correlation-id": corr_id}
    
    # In a real system, we'd pass X-Timeout-Budget in headers. 
    # For now, we set a strict 4.0s timeout here so it fails BEFORE the 
    # upstream 5.0s timeout (if this service was called by another one).
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = await client.get(f"{url}/api/data", headers=headers, timeout=4.0)
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
    # Log the Correlation ID to the console. This simulates logging to Datadog/Splunk.
    corr_id = correlation_id_var.get()
    print(f"[{SERVICE_NAME}] Processing request with Correlation ID: {corr_id}")
    
    # Parse the downstream URLs from the environment variable
    downstreams = [url.strip() for url in DOWNSTREAM_URLS.split(",") if url.strip()]
    
    results = {}
    if downstreams:
        async with httpx.AsyncClient() as client:
            # CONCURRENCY: Create a task for every downstream dependency
            tasks = [fetch_downstream(client, url) for url in downstreams]
            
            # asyncio.gather fires them all simultaneously, not sequentially.
            # If B takes 1s and C takes 1s, the total time is 1s, not 2s.
            responses = await asyncio.gather(*tasks)
            
            for url, response in zip(downstreams, responses):
                name = url.replace("http://", "").split(":")[0]
                results[name] = response

    return {
        "service": SERVICE_NAME,
        "correlation_id": corr_id,
        "dependencies": results
    }