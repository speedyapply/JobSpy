from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class StatusVagaModel(Base):
    __tablename__ = "status_vagas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    vagas = relationship("VagaModel", back_populates="status")

class VagaModel(Base):
    __tablename__ = "vagas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String, nullable=True)
    company = Column(String, nullable=True)
    company_url = Column(String, nullable=True)
    job_url = Column(String, nullable=True, unique=True) # Evita links duplicados futuramente
    location = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    country = Column(String, nullable=True)
    is_remote = Column(Boolean, default=False)
    description = Column(String, nullable=True)
    job_type = Column(String, nullable=True)
    interval = Column(String, nullable=True)
    min_amount = Column(Float, nullable=True)
    max_amount = Column(Float, nullable=True)
    currency = Column(String, nullable=True)
    date_posted = Column(String, nullable=True)
    emails = Column(String, nullable=True)
    # Nova Chave Estrangeira vinculando ao Status (permite nulo se a vaga for nova)
    status_id = Column(Integer, ForeignKey("status_vagas.id"), nullable=True)
    
    # Relacionamento com o modelo de Status
    status = relationship("StatusVagaModel", back_populates="vagas")