import os
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