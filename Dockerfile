FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port (Render will set PORT env var)
EXPOSE 8080

CMD ["python", "bot.py"]