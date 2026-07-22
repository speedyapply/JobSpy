# Variáveis para simplificar alterações futuras
COMPOSE = docker compose
SERVICE_NAME = web

.PHONY: help build up down restart logs ps shell clean scraper migrate migration rollback

# Comando padrão caso digite apenas 'make'
help:
	@echo "Comandos disponíveis no JobSpy:"
	@echo "  make build    - Reconstrói as imagens do Docker (útil após alterar requirements.txt)"
	@echo "  make up       - Sobe os contêineres em segundo plano (detached mode)"
	@echo "  make down     - Para e remove os contêineres ativos"
	@echo "  make restart  - Reinicia os serviços do projeto"
	@echo "  make logs     - Exibe e segue os logs do contêiner em tempo real"
	@echo "  make ps       - Lista os contêineres do projeto e seus status"
	@echo "  make shell    - Abre um terminal interativo Bash dentro do contêiner 'web'"
	@echo "  make scraper  - Executa manualmente o script do scraper dentro do contêiner"
	@echo "  make clean    - Limpa arquivos temporários do Python e caches"

build:
	$(COMPOSE) up -d --build

up:
	$(COMPOSE) up -d
	@echo " Acesse: http://localhost:8000/dashboard"

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs $(SERVICE_NAME) -f

ps:
	$(COMPOSE) ps

shell:
	$(COMPOSE) exec $(SERVICE_NAME) /bin/bash

scraper:
	$(COMPOSE) exec $(SERVICE_NAME) python scraper.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	
# Gera uma nova migration automaticamente comparando o models.py com o Banco
# Uso: make migration m="mensagem da migration"
migration:
	docker compose exec web alembic revision --autogenerate -m "$(m)"

# Aplica todas as migrations pendentes no banco de dados (Equivalente ao php artisan migrate)
migrate:
	docker compose exec web alembic upgrade head

# Reverte a última migration aplicada (Equivalente ao php artisan migrate:rollback)
rollback:
	docker compose exec web alembic downgrade -1