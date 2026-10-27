from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

class ServiceRecord(Base):
    __tablename__ = "services"
    
    # mapped_column replaces the old Column() syntax in SQLAlchemy 2.0
    # It enforces strict Python typing
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    current_version: Mapped[str] = mapped_column(String, default="1.0.0")
    
    # One-to-many relationship: A service has many deployment histories
    deployments: Mapped[list["DeploymentRecord"]] = relationship(back_populates="service")

class DeploymentRecord(Base):
    __tablename__ = "deployments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    version: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String) # e.g., 'pending', 'canary', 'success', 'rolled_back'
    
    service: Mapped["ServiceRecord"] = relationship(back_populates="deployments")