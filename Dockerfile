FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY camtrack camtrack
COPY ui ui
COPY models models
ENV CAMTRACK_TOKEN=""
EXPOSE 8080
# config.json, events/ and references/ live on a mounted volume at /data (see README)
CMD ["python3", "-m", "camtrack", "--host", "0.0.0.0", "--port", "8080", "--config", "/data/config.json"]
