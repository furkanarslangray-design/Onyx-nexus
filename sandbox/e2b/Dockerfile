FROM python:3.11-slim
WORKDIR /app
# Docker CLI'ı yükleyelim ki /var/run/docker.sock üzerinden host'a komut atabilsin
RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "executor.py"]
