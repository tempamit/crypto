FROM python:3.12-slim

# Set environment variables to prevent Python from writing .pyc files 
# and to keep logs flowing in real-time.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (needed for Pillow/Image processing)
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Create a directory for persistent data (SQLite)
RUN mkdir -p /app/data

# This is the start command baked into the image
CMD ["python", "-u", "crypto_engine.py"]