# filepath: /JobSpy/Dockerfile
# Use uma imagem oficial do Python como base
FROM python:3.10-slim-buster

# Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# Copia o arquivo de requisitos e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da sua aplicação para o contêiner
COPY ./app /app

# Comando para rodar a aplicação com Uvicorn
# 'main:app' significa o objeto 'app' dentro do arquivo 'main.py'
# '--host 0.0.0.0' permite que a aplicação seja acessível de fora do contêiner
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]