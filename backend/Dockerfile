FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --retries 8 --timeout 60 -r requirements.txt
COPY app ./app
COPY migrations ./migrations
ENV SCHOOLSYNC_DATA_DIR=/app/data
RUN useradd -m app && mkdir -p /app/data && chown app /app/data
USER app
EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
