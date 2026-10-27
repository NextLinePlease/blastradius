from fastapi import FastAPI, HTTPException
import httpx
import os

SERVICE_NAME = os.getenv("SERVICE_NAME", "service-a")
# By default, we point to the Docker internal DNS name of service-b
DOWNSTREAM_URL = os.getenv("DOWNSTREAM_URL", "http://service-b:8000")

app = FastAPI(title=SERVICE_NAME)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": SERVICE_NAME}

@app.get("/api/aggregate")
async def aggregate_data():
    # Use AsyncClient to prevent blocking the event loop.
    async with httpx.AsyncClient() as client:
        try:
            # We enforce a strict timeout. If downstream is dead, we fail fast.
            response = await client.get(f"{DOWNSTREAM_URL}/api/data", timeout=5.0)
            response.raise_for_status()
            downstream_data = response.json()
        except httpx.RequestError as exc:
            # The network request failed (e.g., service-b is down)
            raise HTTPException(status_code=503, detail=f"Error connecting to downstream: {exc}")
        except httpx.HTTPStatusError as exc:
            # service-b returned a 4xx or 5xx error code
            raise HTTPException(status_code=exc.response.status_code, detail=f"Downstream error: {exc}")
    
    return {
        "message": "Aggregated successfully",
        "service": SERVICE_NAME,
        "downstream_response": downstream_data
    }