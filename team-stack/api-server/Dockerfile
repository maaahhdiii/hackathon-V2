FROM python:3.11-slim

WORKDIR /app

COPY api-server/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY common common
COPY api-server/app.py app.py

EXPOSE 8002

CMD ["python", "app.py"]
