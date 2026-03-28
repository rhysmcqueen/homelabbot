FROM python:3.12-slim

WORKDIR /app

# Create a non-root user to run the bot
RUN useradd -m -u 1000 botuser

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source
COPY bot/ ./bot/

# Create the data directory and hand ownership to the bot user
RUN mkdir -p /app/data && chown botuser:botuser /app/data

USER botuser

ENTRYPOINT ["python", "-m", "bot"]
