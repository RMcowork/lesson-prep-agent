# Runs the lesson-prep agent anywhere. Mount a volume at /data for knowledge, memory, output and the index.
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt ./
COPY rag/requirements.txt rag/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV AGENT_DATA_DIR=/data
VOLUME /data

# Pass keys at run time: docker run -it --env-file .env -v agent-data:/data lesson-prep-agent lesson "data types" 45 english
ENTRYPOINT ["python", "-m", "agent"]
CMD ["chat"]
