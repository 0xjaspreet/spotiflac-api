FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

ENV MUSIC_DIR=/music
ENV MAX_CONCURRENT=3
ENV PATH="/app:${PATH}"

EXPOSE 9118

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9118"]
