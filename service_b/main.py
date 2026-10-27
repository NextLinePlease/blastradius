from fastapi import FastAPI
import os

# We use environment variables so we can reuse this code later for services C, D, E.
SERVICE_NAME = os.getenv("SERVICE_NAME", "service-b")

app = FastAPI(title=SERVICE_NAME)

@app.get("/health")
async def health_check():
    # Standard practice: always have a health endpoint so orchestrators know the app is alive.
    return {"status": "healthy", "service": SERVICE_NAME}

@app.get("/api/data")
async def get_data():
    return {"message": "Data successfully retrieved", "service": SERVICE_NAME}