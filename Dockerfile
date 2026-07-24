# DemoGen Docker Configuration (placeholder)
# Full Docker setup will be added in production deployment phase

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    postgresql-client \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright
RUN python -m playwright install chromium --with-deps

# Copy application
COPY . .

# Create directories
RUN mkdir -p outputs logs

# Expose port
EXPOSE 8000

# Run setup and start server
CMD ["bash", "-c", "python setup.py && python backend/app/main.py"]
