# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
# Playwright needs some system dependencies, but 'playwright install --with-deps' handles most.
# However, for the build process, we might need git or build-essential if any package needs compiling.
RUN apt-get update && apt-get install -y \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set timezone to Asia/Taipei
ENV TZ=Asia/Taipei

# Copy requirements first to leverage cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers and dependencies
# We only need Chromium for this project based on scraper.py usage
RUN playwright install --with-deps chromium

# Copy the rest of the application
COPY . .

# Command to run the application
# We use the schedule flag as this is likely intended for a long-running service on Zeabur
CMD ["python", "main.py", "--schedule"]
