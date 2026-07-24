from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config import settings

# O connect_args é necessário para o SQLite lidar com múltiplas threads no FastAPI
engine = create_engine(
    settings.database_url, 
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependência do FastAPI para injetar a sessão do banco nas rotas
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()