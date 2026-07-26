import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # O Pydantic Settings mapeia automaticamente variáveis em maiúsculo no .env
    # para estas propriedades em minúsculo.
    
    app_name: str = "JobSpy"
    environment: str = "development"
    default_username: str = "Admin"
    
    database_url: str = "sqlite:////app/data/jobs.db"
    db_file_path: str = "/app/data/jobs.db"
    
    scraper_results_wanted: int = 15
    scraper_hours_old: int = 72

    # Configuração para ler do arquivo .env externo
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore" # Ignora outras variáveis do .env que não usamos aqui
    )

# Instanciamos uma vez para ser importada no projeto todo (Singleton)
settings = Settings()

def setup_logging():
    """Configura o logging para a aplicação."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler()  # Log para o console
        ]
    )
    # Diminui a verbosidade de bibliotecas de terceiros
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("multiprocess.pool").setLevel(logging.WARNING)


# Configura o logging assim que este módulo for importado
setup_logging()