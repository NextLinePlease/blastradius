from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

class ServiceDependency(Base):
    """Tracks the DAG edges: Service A depends on Service B."""
    __tablename__ = "service_dependencies"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # ondelete="CASCADE" ensures if we delete a service, its dependencies vanish automatically
    upstream_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    # We store the downstream name as a string because the downstream might not be registered yet!
    downstream_name: Mapped[str] = mapped_column(String, index=True)

class ServiceRecord(Base):
    __tablename__ = "services"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    current_version: Mapped[str] = mapped_column(String, default="1.0.0")
    
    deployments: Mapped[list["DeploymentRecord"]] = relationship(back_populates="service")
    dependencies: Mapped[list["ServiceDependency"]] = relationship(cascade="all, delete-orphan")

class DeploymentRecord(Base):
    __tablename__ = "deployments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    version: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    
    service: Mapped["ServiceRecord"] = relationship(back_populates="deployments")