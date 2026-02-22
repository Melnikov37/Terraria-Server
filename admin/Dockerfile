FROM python:3.11-slim

# System dependencies needed by psutil and screen interactions
RUN apt-get update && apt-get install -y --no-install-recommends \
        screen \
        procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY terraria_admin/ terraria_admin/
COPY templates/ templates/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
