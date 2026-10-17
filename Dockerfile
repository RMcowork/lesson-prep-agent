# Runs the lesson-prep agent anywhere. Mount a volume at /data for knowledge, memory, output, topics and the index.
FROM python:3.13-slim

WORKDIR /app
# Non-root user; /data is created and owned before it is declared a volume
RUN useradd --create-home --uid 1000 app && mkdir /data && chown app:app /data

COPY requirements.txt ./
COPY rag/requirements.txt rag/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV AGENT_DATA_DIR=/data \
    PYTHONUNBUFFERED=1
USER app
VOLUME /data

# Menu:     docker run -it --env-file .env -v agent-data:/data lesson-prep-agent
# Telegram: docker run -d --env-file .env -v agent-data:/data lesson-prep-agent telegram
ENTRYPOINT ["python", "-m", "agent"]
CMD ["menu"]
