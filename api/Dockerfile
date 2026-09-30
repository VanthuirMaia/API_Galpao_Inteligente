FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

# usuário não-root
RUN useradd --system --no-create-home api
USER api

EXPOSE 8000
# proxy-headers: o Traefik termina o TLS e repassa X-Forwarded-*; ele é o único que alcança a porta
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
