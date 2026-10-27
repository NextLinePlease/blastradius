import os
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError # NEW IMPORT
from contextlib import asynccontextmanager

from database import engine, Base, get_db
from models import ServiceRecord

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully.")
    yield
    await engine.dispose()

app = FastAPI(title="BlastRadius Registry", lifespan=lifespan)

@app.post("/services/")
async def register_service(name: str, version: str = "1.0.0", db: AsyncSession = Depends(get_db)):
    # We still do the read-check for standard flow efficiency
    result = await db.execute(select(ServiceRecord).where(ServiceRecord.name == name))
    existing = result.scalars().first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Service already registered")
        
    new_service = ServiceRecord(name=name, current_version=version)
    db.add(new_service)
    
    try:
        await db.commit()
        await db.refresh(new_service)
        return new_service
    except IntegrityError:
        # RACE CONDITION CAUGHT: Another request inserted this name between our check and our commit.
        # We must rollback the poisoned transaction before returning the error.
        await db.rollback()
        raise HTTPException(status_code=400, detail="Service already registered (Concurrent insert detected)")

@app.get("/services/")
async def list_services(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ServiceRecord))
    services = result.scalars().all()
    return services