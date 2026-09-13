FROM python:3.11-slim
WORKDIR /app
# Gerekli bağımlılıklar: Nginx yapılandırması ve Python rotator
RUN apt-get update && apt-get install -y nginx curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Nginx'i ve Python rotator scriptini aynı anda başlatacak bir entrypoint ayarlanmalı
CMD ["bash", "-c", "nginx && python rotator/main.py"]
