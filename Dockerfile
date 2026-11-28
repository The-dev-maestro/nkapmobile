FROM python:3.11-slim

WORKDIR /app/cerveau

COPY cerveau/requirements.txt cerveau/pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY cerveau/ /app/cerveau/

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
