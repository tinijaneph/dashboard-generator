FROM python:3.11-slim
WORKDIR /app
# system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy application code
COPY . .

# Expose port
EXPOSE 8080
# environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# application run
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--timeout", "120", "main:app"]
