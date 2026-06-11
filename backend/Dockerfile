FROM python:3.11-slim

WORKDIR /app

# Install dependencies first — this layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8000

# 0.0.0.0 binds to all interfaces so Docker can route traffic in from the host
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
