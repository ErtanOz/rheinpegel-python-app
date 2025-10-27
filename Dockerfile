FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        fastapi>=0.111 \
        "uvicorn[standard]>=0.29" \
        httpx>=0.27 \
        python-dotenv>=1.0 \
        jinja2>=3.1 \
        pydantic>=2.7 \
        pydantic-settings>=2.4 \
        prometheus-client>=0.20 \
        python-dateutil>=2.9 \
        defusedxml>=0.7

COPY app ./app
COPY data ./data
COPY README.md ./
COPY .env.example ./

RUN adduser --system --group appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
