FROM python:3.12-slim

# opencv-python-headless needs libglib2.0 on slim images
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py handlers.py database.py totp_task.py qr.py ./

# DB (otp_magic.db) is created in CWD — keep it on a volume
WORKDIR /data
CMD ["python", "/app/bot.py"]
