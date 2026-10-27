import os
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from contextlib import asynccontextmanager
from pydantic import BaseModel

from database import engine, Base, get_db
from models import ServiceRecord, ServiceDependency

class ServiceRegisterRequest(BaseModel):
    name: str
    version: str = "1.0.0"
    dependencies: list[str] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully.")
    yield
    await engine.dispose()

app = FastAPI(title="BlastRadius Registry", lifespan=lifespan)

@app.post("/services/")
async def register_service(req: ServiceRegisterRequest, db: AsyncSession = Depends(get_db)):
    # 1. UPSERT THE SERVICE: This is atomic and race-condition proof at the Postgres level.
    # If the name exists, update the version. If not, insert it.
    stmt = pg_insert(ServiceRecord).values(name=req.name, current_version=req.version)
    stmt = stmt.on_conflict_do_update(
        index_elements=['name'],
        set_={'current_version': req.version}
    ).returning(ServiceRecord.id)
    
    result = await db.execute(stmt)
    service_id = result.scalar_one()
    
    # 2. OVERWRITE DEPENDENCIES: Delete old edges and write the new ones.
    await db.execute(delete(ServiceDependency).where(ServiceDependency.upstream_id == service_id))
    
    if req.dependencies:
        dep_records = [
            ServiceDependency(upstream_id=service_id, downstream_name=dep) 
            for dep in req.dependencies
        ]
        db.add_all(dep_records)
        
    await db.commit()
    return {"message": "Registered successfully", "service_id": service_id, "dependencies": req.dependencies}

@app.get("/dag/")
async def get_active_dag(db: AsyncSession = Depends(get_db)):
    """Returns the entire active dependency graph of the cluster."""
    result = await db.execute(select(ServiceRecord.name, ServiceDependency.downstream_name)
                              .outerjoin(ServiceDependency, ServiceRecord.id == ServiceDependency.upstream_id))
    
    # Format the SQL rows into a clean dictionary: {"service-a": ["service-b", "service-c"]}
    dag = {}
    for upstream, downstream in result.all():
        if upstream not in dag:
            dag[upstream] = []
        if downstream:
            dag[upstream].append(downstream)
            
    return dag