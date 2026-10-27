FROM python:3.11-slim

WORKDIR /app

# PYTHONUNBUFFERED=1 prevents Python from buffering stdout/stderr. 
# Without this, Docker logs are delayed, making debugging a nightmare.
ENV PYTHONUNBUFFERED=1 

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bind to 0.0.0.0, not localhost. In Docker, localhost means the container itself.
# To let outside traffic (or other containers) in, you must bind to 0.0.0.0.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]