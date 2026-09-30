FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

# usuário não-root
RUN useradd --system --no-create-home ingestor
USER ingestor

CMD ["python", "main.py"]
