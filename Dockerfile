FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Madrid

WORKDIR /app

# the library first, so editing the backend or the searches doesn't reinstall it
COPY pyproject.toml README.md LICENSE ./
COPY jobspy ./jobspy
RUN pip install . "starlette>=0.37" "uvicorn>=0.29" "pypdf>=4"

COPY runner/api.py runner/run.py runner/match.py runner/store.py ./
COPY runner/searches.json runner/profile.json ./

RUN useradd --create-home jobspy && mkdir /data && chown jobspy /data
USER jobspy
VOLUME /data
EXPOSE 8000

CMD ["python", "api.py"]
